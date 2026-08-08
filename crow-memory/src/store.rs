//! LanceDB persistence — same 4-table schema as Python crow-memory/store.py.
//!
//! Tables: prompts, agents, messages, images.

use std::path::Path;
use std::sync::Arc;

use arrow_array::{
    Array, FixedSizeListArray, Float32Array, Int64Array, ListArray, RecordBatch, StringArray,
};
use arrow_schema::{DataType, Field, Schema};
use lancedb::connection::Connection;
use lancedb::query::{ExecutableQuery, QueryBase};
use lancedb::table::Table;
use tokio::sync::Mutex;

use crate::embed::{self, EmbedConfig};

fn now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}

/// Generate a short random slug (e.g. "brave-fox-42").
pub fn generate_slug() -> String {
    use rand::Rng;
    const ADJ: &[&str] = &[
        "brave", "calm", "dark", "eager", "fair", "glad", "keen", "lush", "mild", "neat", "pale",
        "rare", "sage", "tall", "vast", "warm", "zany", "bold", "cool", "dull",
    ];
    const NOUN: &[&str] = &[
        "fox", "owl", "elk", "ram", "hen", "cod", "ant", "bee", "cat", "dog", "emu", "fly", "gnu",
        "hog", "ibis", "jay", "koi", "lynx", "mole", "newt",
    ];
    let mut rng = rand::rng();
    let a = ADJ[rng.random_range(0..ADJ.len())];
    let n = NOUN[rng.random_range(0..NOUN.len())];
    let num: u16 = rng.random_range(0..100);
    format!("{a}-{n}-{num}")
}

// ---- Schemas ---------------------------------------------------------------

fn prompts_schema() -> Arc<Schema> {
    Arc::new(Schema::new(vec![
        Field::new("id", DataType::Utf8, false),
        Field::new("name", DataType::Utf8, false),
        Field::new("template", DataType::Utf8, false),
        Field::new("template_hash", DataType::Utf8, false),
        Field::new("created_at", DataType::Utf8, false),
    ]))
}

fn agents_schema() -> Arc<Schema> {
    Arc::new(Schema::new(vec![
        Field::new("agent_id", DataType::Utf8, false),
        Field::new("session_id", DataType::Utf8, false),
        Field::new("agent_idx", DataType::Int64, false),
        Field::new("cwd", DataType::Utf8, false),
        Field::new("prompt_id", DataType::Utf8, false),
        Field::new("prompt_args", DataType::Utf8, false),
        Field::new("system_prompt", DataType::Utf8, false),
        Field::new("tool_definitions", DataType::Utf8, false),
        Field::new("request_params", DataType::Utf8, false),
        Field::new("model_identifier", DataType::Utf8, false),
        Field::new("status", DataType::Utf8, false),
        Field::new("created_at", DataType::Utf8, false),
    ]))
}

fn mv_field() -> Field {
    Field::new(
        "mv",
        DataType::List(Arc::new(Field::new(
            "item",
            DataType::FixedSizeList(
                Arc::new(Field::new("item", DataType::Float32, true)),
                embed::EMBED_DIM as i32,
            ),
            true,
        ))),
        true,
    )
}

fn messages_schema() -> Arc<Schema> {
    Arc::new(Schema::new(vec![
        Field::new("id", DataType::Int64, false),
        Field::new("agent_id", DataType::Utf8, false),
        Field::new("created_at", DataType::Utf8, false),
        Field::new("data", DataType::Utf8, false),
        Field::new("role", DataType::Utf8, false),
        Field::new("prompt_tokens", DataType::Int64, false),
        Field::new("completion_tokens", DataType::Int64, false),
        Field::new("total_tokens", DataType::Int64, false),
        mv_field(),
    ]))
}

fn images_schema() -> Arc<Schema> {
    Arc::new(Schema::new(vec![
        Field::new("image_id", DataType::Utf8, false),
        Field::new("mime", DataType::Utf8, false),
        Field::new("data", DataType::LargeBinary, false),
        Field::new("w", DataType::Int64, false),
        Field::new("h", DataType::Int64, false),
        Field::new("created_at", DataType::Utf8, false),
        mv_field(),
    ]))
}

// ---- Store -----------------------------------------------------------------

pub struct MemoryStore {
    db: Connection,
    prompts: Table,
    agents: Table,
    messages: Table,
    #[allow(dead_code)]
    images: Table,
    http: reqwest::Client,
    embed_config: EmbedConfig,
    /// Last allocated message id. Seeded once from max(id) at open; the
    /// mutex makes id-allocation + insert atomic, so concurrent writes
    /// can never hand out the same id.
    next_msg_id: Mutex<i64>,
}

impl MemoryStore {
    pub async fn open(path: &Path, embed_config: EmbedConfig) -> anyhow::Result<Self> {
        let db = lancedb::connect(path.to_str().unwrap_or_default())
            .execute()
            .await?;
        let prompts = open_or_create(&db, "prompts", prompts_schema()).await?;
        let agents = open_or_create(&db, "agents", agents_schema()).await?;
        let messages = open_or_create(&db, "messages", messages_schema()).await?;
        let images = open_or_create(&db, "images", images_schema()).await?;
        let http = embed_config.client();
        let next_msg_id = Mutex::new(max_message_id(&messages).await?);
        Ok(Self {
            db,
            prompts,
            agents,
            messages,
            images,
            http,
            embed_config,
            next_msg_id,
        })
    }

    // ---- prompts ----

    pub async fn lookup_or_create_prompt(
        &self,
        template: &str,
        name: &str,
    ) -> anyhow::Result<String> {
        let th = template_hash(template);
        let rows = query_all(&self.prompts, &format!("template_hash = '{th}'")).await?;
        if let Some(batch) = rows.first() {
            if batch.num_rows() > 0 {
                let ids = batch
                    .column(0)
                    .as_any()
                    .downcast_ref::<StringArray>()
                    .unwrap();
                return Ok(ids.value(0).to_string());
            }
        }
        let prompt_id = generate_slug();
        let schema = prompts_schema();
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(StringArray::from(vec![prompt_id.as_str()])),
                Arc::new(StringArray::from(vec![name])),
                Arc::new(StringArray::from(vec![template])),
                Arc::new(StringArray::from(vec![th.as_str()])),
                Arc::new(StringArray::from(vec![now_iso()])),
            ],
        )?;
        self.prompts.add(batch).execute().await?;
        Ok(prompt_id)
    }

    pub async fn get_prompt(&self, prompt_id: &str) -> anyhow::Result<Option<PromptRecord>> {
        let rows = query_all(
            &self.prompts,
            &format!("id = '{}'", escape_sql(prompt_id)),
        )
        .await?;
        for batch in &rows {
            if batch.num_rows() > 0 {
                let ids = col_str(batch, 0);
                let names = col_str(batch, 1);
                let templates = col_str(batch, 2);
                return Ok(Some(PromptRecord {
                    id: ids.value(0).to_string(),
                    name: names.value(0).to_string(),
                    template: templates.value(0).to_string(),
                }));
            }
        }
        Ok(None)
    }

    // ---- agents ----

    #[allow(clippy::too_many_arguments)]
    pub async fn create_agent(
        &self,
        agent_id: &str,
        session_id: &str,
        agent_idx: i64,
        cwd: &str,
        prompt_id: &str,
        prompt_args: &serde_json::Value,
        system_prompt: &str,
        tool_definitions: &serde_json::Value,
        request_params: &serde_json::Value,
        model_identifier: &str,
    ) -> anyhow::Result<()> {
        let schema = agents_schema();
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(StringArray::from(vec![agent_id])),
                Arc::new(StringArray::from(vec![session_id])),
                Arc::new(Int64Array::from(vec![agent_idx])),
                Arc::new(StringArray::from(vec![cwd])),
                Arc::new(StringArray::from(vec![prompt_id])),
                Arc::new(StringArray::from(vec![prompt_args.to_string()])),
                Arc::new(StringArray::from(vec![system_prompt])),
                Arc::new(StringArray::from(vec![tool_definitions.to_string()])),
                Arc::new(StringArray::from(vec![request_params.to_string()])),
                Arc::new(StringArray::from(vec![model_identifier])),
                Arc::new(StringArray::from(vec!["active"])),
                Arc::new(StringArray::from(vec![now_iso()])),
            ],
        )?;
        self.agents.add(batch).execute().await?;
        Ok(())
    }

    pub async fn get_agent(&self, agent_id: &str) -> anyhow::Result<Option<AgentRecord>> {
        let rows = query_all(
            &self.agents,
            &format!("agent_id = '{}'", escape_sql(agent_id)),
        )
        .await?;
        for batch in &rows {
            if batch.num_rows() > 0 {
                return Ok(Some(parse_agent_row(batch, 0)));
            }
        }
        Ok(None)
    }

    pub async fn list_agents(&self, session_id: Option<&str>) -> anyhow::Result<Vec<AgentRecord>> {
        let filter = session_id
            .map(|s| format!("session_id = '{}'", escape_sql(s)))
            .unwrap_or_else(|| "agent_idx >= 0".into());
        let rows = query_all(&self.agents, &filter).await?;
        let mut out = Vec::new();
        for batch in &rows {
            for i in 0..batch.num_rows() {
                out.push(parse_agent_row(batch, i));
            }
        }
        Ok(out)
    }

    pub async fn get_max_agent_idx(&self, session_id: &str) -> anyhow::Result<i64> {
        let rows = query_all(
            &self.agents,
            &format!("session_id = '{}'", escape_sql(session_id)),
        )
        .await?;
        let mut max_idx: i64 = -1;
        for batch in &rows {
            let idxs = batch
                .column(2)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            for i in 0..batch.num_rows() {
                if idxs.value(i) > max_idx {
                    max_idx = idxs.value(i);
                }
            }
        }
        Ok(max_idx)
    }

    // ---- messages ----

    pub async fn add_message(
        &self,
        agent_id: &str,
        message: &serde_json::Value,
        usage: Option<&serde_json::Value>,
    ) -> anyhow::Result<i64> {
        // Fail fast if the table is broken: append would otherwise silently
        // recreate it from the cached manifest, diverging from history.
        probe_messages_table(&self.messages).await?;

        // Embedding happens BEFORE the id lock — the network round-trip is
        // the slow part, and it doesn't depend on the id.
        let text = embed::text_for_embedding(message);
        let mv = self.embed_config.embed_text(&self.http, &text).await;

        let role = message
            .get("role")
            .and_then(|r| r.as_str())
            .unwrap_or("unknown");
        let data_json = serde_json::to_string(message)?;

        let pt = usage
            .and_then(|u| u.get("prompt_tokens"))
            .and_then(|v| v.as_i64())
            .unwrap_or(0);
        let ct = usage
            .and_then(|u| u.get("completion_tokens"))
            .and_then(|v| v.as_i64())
            .unwrap_or(0);
        let tt = usage
            .and_then(|u| u.get("total_tokens"))
            .and_then(|v| v.as_i64())
            .unwrap_or(0);

        let schema = messages_schema();
        let mv_array = build_mv_array(&[mv]);

        // Id allocation + insert under one lock: no scan per write, no
        // duplicate ids under concurrent requests.
        let mut next = self.next_msg_id.lock().await;
        let msg_id = *next + 1;
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(Int64Array::from(vec![msg_id])),
                Arc::new(StringArray::from(vec![agent_id])),
                Arc::new(StringArray::from(vec![now_iso()])),
                Arc::new(StringArray::from(vec![data_json])),
                Arc::new(StringArray::from(vec![role])),
                Arc::new(Int64Array::from(vec![pt])),
                Arc::new(Int64Array::from(vec![ct])),
                Arc::new(Int64Array::from(vec![tt])),
                Arc::new(mv_array),
            ],
        )?;
        self.messages.add(batch).execute().await?;
        *next = msg_id;
        Ok(msg_id)
    }

    pub async fn load_messages(
        &self,
        agent_id: &str,
    ) -> anyhow::Result<Vec<serde_json::Value>> {
        let rows = query_all(
            &self.messages,
            &format!("agent_id = '{}'", escape_sql(agent_id)),
        )
        .await?;
        let mut msgs: Vec<(i64, serde_json::Value)> = Vec::new();
        for batch in &rows {
            let ids = batch
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            let data = col_str(batch, 3);
            for i in 0..batch.num_rows() {
                if let Ok(v) = serde_json::from_str(data.value(i)) {
                    msgs.push((ids.value(i), v));
                }
            }
        }
        msgs.sort_by_key(|(id, _)| *id);
        Ok(msgs.into_iter().map(|(_, v)| v).collect())
    }

    pub async fn query_messages_by_agent(
        &self,
        agent_id: &str,
        order_asc: bool,
        limit: usize,
        role: Option<&str>,
    ) -> anyhow::Result<Vec<MessageRecord>> {
        // Project away the multivector column — full-row scans read gigabytes.
        use futures::TryStreamExt;
        use lancedb::query::Select;
        let mut filter = format!("agent_id = '{}'", escape_sql(agent_id));
        if let Some(r) = role {
            filter.push_str(&format!(" AND role = '{}'", escape_sql(r)));
        }
        let stream = self
            .messages
            .query()
            .only_if(&filter)
            .select(Select::columns(&[
                "id",
                "agent_id",
                "created_at",
                "data",
                "role",
            ]))
            .limit(1_000_000)
            .execute()
            .await?;
        let rows: Vec<RecordBatch> = stream.try_collect().await?;
        let mut out = Vec::new();
        for batch in &rows {
            let ids = batch
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            let agent_ids = col_str(batch, 1);
            let created_ats = col_str(batch, 2);
            let data = col_str(batch, 3);
            let roles = col_str(batch, 4);
            for i in 0..batch.num_rows() {
                out.push(MessageRecord {
                    id: ids.value(i),
                    agent_id: agent_ids.value(i).to_string(),
                    created_at: created_ats.value(i).to_string(),
                    data: serde_json::from_str(data.value(i)).unwrap_or_default(),
                    role: roles.value(i).to_string(),
                    score: None,
                });
            }
        }
        if order_asc {
            out.sort_by_key(|m| m.id);
        } else {
            out.sort_by(|a, b| b.id.cmp(&a.id));
        }
        out.truncate(limit);
        Ok(out)
    }

    /// Semantic search across all messages using multivector ColBERT MaxSim.
    /// `role` narrows matches to one message role (pre-filter, pushed into
    /// the LanceDB query).
    pub async fn search_messages(
        &self,
        query: &str,
        limit: usize,
        role: Option<&str>,
    ) -> anyhow::Result<Vec<MessageRecord>> {
        let mv = self.embed_config.embed_text(&self.http, query).await;
        if mv.is_empty() {
            // Fallback: no embedding available, return recent messages
            return self.recent_messages(limit, role).await;
        }
        // Multivector late-interaction (MaxSim) search: one query vector per
        // token against the List<FixedSizeList[128]> mv column. Pad/truncate
        // each token to EMBED_DIM to match the stored FSL width.
        let pad = |v: &Vec<f32>| -> Vec<f32> {
            let mut t = v[..v.len().min(embed::EMBED_DIM)].to_vec();
            t.resize(embed::EMBED_DIM, 0.0);
            t
        };
        let mut q = self
            .messages
            .query()
            .nearest_to(pad(&mv[0]))?
            .column("mv");
        for tok in &mv[1..] {
            q = q.add_query_vector(pad(tok))?;
        }
        if let Some(r) = role {
            q = q.only_if(&format!("role = '{}'", escape_sql(r)));
        }
        use futures::TryStreamExt;
        let stream = q.limit(limit).execute().await?;
        let batches: Vec<RecordBatch> = stream.try_collect().await?;
        let mut out = Vec::new();
        for batch in &batches {
            let ids = batch
                .column_by_name("id")
                .and_then(|c| c.as_any().downcast_ref::<Int64Array>());
            let agent_ids = batch
                .column_by_name("agent_id")
                .and_then(|c| c.as_any().downcast_ref::<StringArray>());
            let created_ats = batch
                .column_by_name("created_at")
                .and_then(|c| c.as_any().downcast_ref::<StringArray>());
            let data = batch
                .column_by_name("data")
                .and_then(|c| c.as_any().downcast_ref::<StringArray>());
            let roles = batch
                .column_by_name("role")
                .and_then(|c| c.as_any().downcast_ref::<StringArray>());
            let distances = batch
                .column_by_name("_distance")
                .and_then(|c| c.as_any().downcast_ref::<Float32Array>());
            if let (Some(ids), Some(aids), Some(cas), Some(dat), Some(rol)) =
                (ids, agent_ids, created_ats, data, roles)
            {
                for i in 0..batch.num_rows() {
                    out.push(MessageRecord {
                        id: ids.value(i),
                        agent_id: aids.value(i).to_string(),
                        created_at: cas.value(i).to_string(),
                        data: serde_json::from_str(dat.value(i)).unwrap_or_default(),
                        role: rol.value(i).to_string(),
                        score: distances.map(|d| d.value(i)),
                    });
                }
            }
        }
        Ok(out)
    }

    async fn recent_messages(
        &self,
        limit: usize,
        role: Option<&str>,
    ) -> anyhow::Result<Vec<MessageRecord>> {
        let filter = match role {
            Some(r) => format!("id >= 0 AND role = '{}'", escape_sql(r)),
            None => "id >= 0".to_string(),
        };
        let rows = query_all(&self.messages, &filter).await?;
        let mut out = Vec::new();
        for batch in &rows {
            let ids = batch
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            let agent_ids = col_str(batch, 1);
            let created_ats = col_str(batch, 2);
            let data = col_str(batch, 3);
            let roles = col_str(batch, 4);
            for i in 0..batch.num_rows() {
                out.push(MessageRecord {
                    id: ids.value(i),
                    agent_id: agent_ids.value(i).to_string(),
                    created_at: created_ats.value(i).to_string(),
                    data: serde_json::from_str(data.value(i)).unwrap_or_default(),
                    role: roles.value(i).to_string(),
                    score: None,
                });
            }
        }
        out.sort_by(|a, b| b.id.cmp(&a.id));
        out.truncate(limit);
        Ok(out)
    }

    /// List sessions ordered by most-recent message activity.
    pub async fn list_sessions(
        &self,
        limit: usize,
        offset: usize,
    ) -> anyhow::Result<Vec<SessionInfo>> {
        let agents = self.list_agents(None).await?;
        if agents.is_empty() {
            return Ok(Vec::new());
        }

        let mut sess_map: std::collections::HashMap<String, Vec<&AgentRecord>> =
            std::collections::HashMap::new();
        for a in &agents {
            sess_map.entry(a.session_id.clone()).or_default().push(a);
        }

        // Per-session message stats + the max-timestamp row (last_message),
        // tracked in one pass over the scan. `data` kept as a string; parsed
        // once per session at the end, not once per message.
        struct LastMsg {
            id: i64,
            agent_id: String,
            created_at: String,
            data: String,
            role: String,
        }
        struct MsgStats {
            count: usize,
            last: LastMsg,
        }

        // Project to the scalar columns only — query_all would pull the
        // multi-KB mv multivector blob for every message row.
        let all_msgs = query_columns(&self.messages, "id >= 0", MESSAGE_SCALAR_COLUMNS).await?;
        let mut msg_stats: std::collections::HashMap<String, MsgStats> =
            std::collections::HashMap::new();

        let agent_to_sess: std::collections::HashMap<&str, &str> = agents
            .iter()
            .map(|a| (a.agent_id.as_str(), a.session_id.as_str()))
            .collect();

        for batch in &all_msgs {
            let ids = batch
                .column(0)
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap();
            let agent_ids = col_str(batch, 1);
            let created_ats = col_str(batch, 2);
            let data = col_str(batch, 3);
            let roles = col_str(batch, 4);
            for i in 0..batch.num_rows() {
                let aid = agent_ids.value(i);
                let Some(&sid) = agent_to_sess.get(aid) else {
                    continue;
                };
                let ts = created_ats.value(i).to_string();
                let sid = sid.to_string();
                let entry = msg_stats.entry(sid).or_insert_with(|| MsgStats {
                    count: 0,
                    last: LastMsg {
                        id: ids.value(i),
                        agent_id: aid.to_string(),
                        created_at: ts.clone(),
                        data: data.value(i).to_string(),
                        role: roles.value(i).to_string(),
                    },
                });
                entry.count += 1;
                if ts > entry.last.created_at {
                    entry.last = LastMsg {
                        id: ids.value(i),
                        agent_id: aid.to_string(),
                        created_at: ts,
                        data: data.value(i).to_string(),
                        role: roles.value(i).to_string(),
                    };
                }
            }
        }

        let mut sessions: Vec<SessionInfo> = sess_map
            .iter()
            .map(|(sid, agents)| {
                let newest = agents.iter().max_by_key(|a| &a.created_at).unwrap();
                let mut idxs: Vec<i64> = agents.iter().map(|a| a.agent_idx).collect();
                idxs.sort_unstable();
                idxs.dedup();
                let (last_activity, message_count, last_role, last_message) =
                    match msg_stats.get(sid.as_str()) {
                        Some(st) => {
                            let lm = MessageRecord {
                                id: st.last.id,
                                agent_id: st.last.agent_id.clone(),
                                created_at: st.last.created_at.clone(),
                                data: serde_json::from_str(&st.last.data)
                                    .unwrap_or_default(),
                                role: st.last.role.clone(),
                                score: None,
                            };
                            (lm.created_at.clone(), st.count, lm.role.clone(), Some(lm))
                        }
                        None => (newest.created_at.clone(), 0, String::new(), None),
                    };
                SessionInfo {
                    session_id: sid.clone(),
                    last_activity,
                    message_count,
                    agent_count: agents.len(),
                    last_role,
                    cwd: newest.cwd.clone(),
                    model_identifier: newest.model_identifier.clone(),
                    agent_idxs: idxs,
                    last_message,
                }
            })
            .collect();

        sessions.sort_by(|a, b| b.last_activity.cmp(&a.last_activity));
        let page: Vec<SessionInfo> = sessions.into_iter().skip(offset).take(limit).collect();
        Ok(page)
    }

    /// Get sessions matching a cwd.
    pub async fn get_sessions_by_cwd(&self, cwd: &str) -> anyhow::Result<Vec<SessionInfo>> {
        let agents = self.list_agents(None).await?;
        let matching: Vec<&AgentRecord> = agents
            .iter()
            .filter(|a| {
                a.prompt_args
                    .get("workspace")
                    .and_then(|w| w.as_str())
                    .map(|w| w == cwd)
                    .unwrap_or(false)
            })
            .collect();

        let mut out = Vec::new();
        for agent in matching {
            out.push(SessionInfo {
                session_id: agent.session_id.clone(),
                last_activity: agent.created_at.clone(),
                message_count: 0,
                agent_count: 1,
                last_role: String::new(),
                cwd: cwd.to_string(),
                model_identifier: agent.model_identifier.clone(),
                agent_idxs: vec![agent.agent_idx],
                last_message: None,
            });
        }
        Ok(out)
    }
}

// ---- Records (wire types live in crow-memory-types) ------------------------

pub use crow_memory_types::{AgentRecord, MessageRecord, PromptRecord, SessionInfo};

// ---- Helpers ---------------------------------------------------------------

async fn open_or_create(
    db: &Connection,
    name: &str,
    schema: Arc<Schema>,
) -> anyhow::Result<Table> {
    match db.open_table(name).execute().await {
        Ok(t) => Ok(t),
        Err(_) => {
            let empty = RecordBatch::new_empty(schema);
            Ok(db.create_table(name, empty).execute().await?)
        }
    }
}

async fn query_all(table: &Table, filter: &str) -> anyhow::Result<Vec<RecordBatch>> {
    use futures::TryStreamExt;
    let stream = table
        .query()
        .only_if(filter)
        .limit(1_000_000)
        .execute()
        .await?;
    let batches: Vec<RecordBatch> = stream.try_collect().await?;
    Ok(batches)
}

/// The messages columns every scan-based reader uses (id, agent_id,
/// created_at, data, role) — everything except the multivector blob.
const MESSAGE_SCALAR_COLUMNS: &[&str] = &["id", "agent_id", "created_at", "data", "role"];

/// Like `query_all`, but projects to `columns` instead of selecting every
/// column — full-row scans read gigabytes once the mv blobs are in play.
async fn query_columns(
    table: &Table,
    filter: &str,
    columns: &[&str],
) -> anyhow::Result<Vec<RecordBatch>> {
    use futures::TryStreamExt;
    use lancedb::query::Select;
    let stream = table
        .query()
        .only_if(filter)
        .select(Select::columns(columns))
        .limit(1_000_000)
        .execute()
        .await?;
    let batches: Vec<RecordBatch> = stream.try_collect().await?;
    Ok(batches)
}

/// Cheap read probe (limit 1, `id` only) — fails fast if the table is
/// unreadable (e.g. its Lance directory was deleted), before we spend an
/// embedding round-trip and let append silently recreate the table.
async fn probe_messages_table(table: &Table) -> anyhow::Result<()> {
    use futures::TryStreamExt;
    use lancedb::query::Select;
    let stream = table
        .query()
        .select(Select::columns(&["id"]))
        .limit(1)
        .execute()
        .await?;
    let _: Vec<RecordBatch> = stream.try_collect().await?;
    Ok(())
}

/// max(id) over the messages table, projecting the `id` column only.
/// Seeds the id counter once at store open.
async fn max_message_id(table: &Table) -> anyhow::Result<i64> {
    let rows = query_columns(table, "id >= 0", &["id"]).await?;
    let mut max_id: i64 = 0;
    for batch in &rows {
        let ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap();
        for i in 0..batch.num_rows() {
            if ids.value(i) > max_id {
                max_id = ids.value(i);
            }
        }
    }
    Ok(max_id)
}

fn col_str(batch: &RecordBatch, idx: usize) -> &StringArray {
    batch
        .column(idx)
        .as_any()
        .downcast_ref::<StringArray>()
        .unwrap()
}

fn parse_agent_row(batch: &RecordBatch, i: usize) -> AgentRecord {
    let s = |idx: usize| col_str(batch, idx).value(i).to_string();
    let idxs = batch
        .column(2)
        .as_any()
        .downcast_ref::<Int64Array>()
        .unwrap();
    AgentRecord {
        agent_id: s(0),
        session_id: s(1),
        agent_idx: idxs.value(i),
        cwd: s(3),
        prompt_id: s(4),
        prompt_args: serde_json::from_str(&s(5)).unwrap_or_default(),
        system_prompt: s(6),
        tool_definitions: serde_json::from_str(&s(7)).unwrap_or_default(),
        request_params: serde_json::from_str(&s(8)).unwrap_or_default(),
        model_identifier: s(9),
        status: s(10),
        created_at: s(11),
    }
}

fn template_hash(template: &str) -> String {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    h.update(template.as_bytes());
    format!("sha256:{:x}", h.finalize())
}

fn escape_sql(s: &str) -> String {
    s.replace('\'', "''")
}

/// Build a ListArray of FixedSizeList<Float32, 128> from multivector data.
fn build_mv_array(mvs: &[Vec<Vec<f32>>]) -> ListArray {
    let dim = embed::EMBED_DIM as i32;
    let inner_field = Arc::new(Field::new("item", DataType::Float32, true));
    let fsl_field = Arc::new(Field::new(
        "item",
        DataType::FixedSizeList(inner_field.clone(), dim),
        true,
    ));

    let mut offsets: Vec<i32> = vec![0];
    let mut all_floats: Vec<f32> = Vec::new();
    let mut validity: Vec<bool> = Vec::new();

    for mv in mvs {
        if mv.is_empty() {
            offsets.push(offsets.last().copied().unwrap_or(0));
            validity.push(false);
        } else {
            for token_vec in mv {
                all_floats.extend_from_slice(token_vec);
                let pad = embed::EMBED_DIM.saturating_sub(token_vec.len());
                all_floats.extend(std::iter::repeat_n(0.0f32, pad));
            }
            offsets.push(offsets.last().unwrap() + mv.len() as i32);
            validity.push(true);
        }
    }

    let values = Float32Array::from(all_floats);
    let fsl = FixedSizeListArray::try_new(inner_field, dim, Arc::new(values), None).unwrap();

    let offsets =
        arrow_buffer::OffsetBuffer::new(offsets.into_iter().collect::<Vec<i32>>().into());

    let null_buf = if validity.iter().all(|&v| v) {
        None
    } else {
        Some(arrow_buffer::NullBuffer::from(validity))
    };

    ListArray::try_new(fsl_field, offsets, Arc::new(fsl), null_buf).unwrap()
}
