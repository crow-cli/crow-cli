//! send_queue: App methods for the send_queue surface (Phase 2 split).

use super::*;
use std::time::Instant;
use crate::bus::{AppEvent, Cmd};
use crate::controller::Controller;

impl App {
    pub(crate) fn queue_editing(&self) -> bool {
        self.queue_edit.is_some()
    }

    pub(crate) fn queue_selecting(&self) -> bool {
        self.queue_selection.is_some()
    }

    pub(crate) fn queue_delete_confirming(&self) -> bool {
        self.queue_edit
            .as_ref()
            .is_some_and(|edit| edit.delete_confirm)
    }

    pub(crate) fn queue_previews(&self, limit: usize) -> Vec<QueuePreview> {
        let editing_id = self.queue_edit.as_ref().map(|edit| edit.prompt_id);
        let focused = self.queue_selection.or_else(|| {
            editing_id.and_then(|id| self.prompt_queue.iter().position(|prompt| prompt.id == id))
        });
        let start = if limit == 0 || self.prompt_queue.len() <= limit {
            0
        } else {
            focused
                .unwrap_or(0)
                .saturating_sub(limit - 1)
                .min(self.prompt_queue.len() - limit)
        };
        self.prompt_queue
            .iter()
            .enumerate()
            .skip(start)
            .take(if limit == 0 {
                self.prompt_queue.len()
            } else {
                limit
            })
            .map(|(index, prompt)| {
                let mut parts = Vec::new();
                for block in &prompt.blocks {
                    match block {
                        StagedBlock::Text(text) => {
                            let text = text.split_whitespace().collect::<Vec<_>>().join(" ");
                            if !text.is_empty() {
                                parts.push(text);
                            }
                        }
                        StagedBlock::Image(image) => parts.push(format!("▣ {}", image.name)),
                    }
                }
                QueuePreview {
                    id: prompt.id,
                    ordinal: index + 1,
                    summary: if parts.is_empty() {
                        "empty prompt".into()
                    } else {
                        parts.join(" ")
                    },
                    selected: self.queue_selection == Some(index),
                    editing: editing_id == Some(prompt.id),
                }
            })
            .collect()
    }


    pub(crate) fn submit(&mut self, ctl: &Controller) {
        // A pending @file browser never survives a send.
        self.file_menu = None;
        let text = self.input.buf().trim().to_string();
        // Client namespaces don't take images — keep the chips editable
        // instead of silently dropping them.
        if !self.pending_images.is_empty() && (text.starts_with('/') || text.starts_with('!')) {
            self.show_tip(
                self.locale.tr(
                    "send or delete the [image] chips first — /commands and !shell don't take images",
                    "先发送或删除 [image] 标记 —— /命令 和 !shell 不接受图片",
                ),
            );
            return;
        }
        if let Some(cmdline) = text.strip_prefix('/') {
            let mut parts = cmdline.splitn(2, ' ');
            let name = parts.next().unwrap_or("").to_string();
            let arg = parts.next().unwrap_or("").trim().to_string();
            // Host skills share the '/' namespace (builtins win a name): a
            // skill line ships as an ordinary prompt — the host's pre-step
            // boundary recognizes the leading /name and injects the body.
            let builtin = SLASH_COMMANDS.iter().any(|c| c.name == name);
            let acp_client_command = self
                .skills
                .iter()
                .any(|command| command.name == name && command.client_command);
            if !builtin && (self.plugin_command_active(&name) || acp_client_command) {
                self.input.history.push(text);
                self.input.clear();
                ctl.send(Cmd::InvokePluginCommand { name, args: arg });
                return;
            }
            if !builtin && self.skills.iter().any(|s| s.name == name) {
                self.input.history.push(text.clone());
                self.input.clear();
                self.send_agent_text(text, ctl);
                return;
            }
            self.input.history.push(text.clone());
            self.input.clear();
            self.run_slash(&name, &arg, ctl);
            return;
        }
        if let Some(cmd) = text.strip_prefix('!') {
            let cmd = cmd.trim().to_string();
            if !cmd.is_empty() {
                self.input.history.push(text.clone());
                self.input.clear();
                self.run_local_shell(cmd);
            }
            return;
        }

        // Inline [image n] chips ride along with the prompt text (or send
        // alone): chip order = block order (图文交替).
        if !self.pending_images.is_empty() {
            self.input.history.push(self.input.buf());
            let staged = self.take_staged_blocks();
            self.input.clear();
            self.send_staged(staged, ctl);
            return;
        }

        if text.is_empty() {
            return;
        }
        self.input.history.push(text.clone());
        self.input.clear();
        self.send_agent_text(text, ctl);
    }

    /// Send raw text as an agent prompt (shared by submit and command
    /// passthroughs like /plan).
    pub(crate) fn send_agent_text(&mut self, text: String, ctl: &Controller) {
        self.show_banner = false;
        // An unbound tab (placeholder id awaiting session/new·load) must not
        // send: acp.rs rejects ids it never bound. Hold the prompt in the
        // queue; the SessionBound handler dispatches it with the real id.
        let running = self.state == RunState::Running
            || self.prompt_pending
            || self.queued > 0
            || !self.session_bound;
        if running {
            let id = self.next_prompt_id();
            self.prompt_queue.push_back(ClientQueuedPrompt {
                id,
                blocks: vec![StagedBlock::Text(text.clone())],
            });
            self.queued += 1;
            self.show_tip(self.locale.tr(
                "queued · empty enter sends first · alt+↑ edit",
                "已排队 · 空输入按 enter 发送队首 · alt+↑ 编辑",
            ));
        } else {
            self.transcript.push_user(text.clone(), false);
            self.prompt_pending = true;
            self.state = RunState::Starting;
            self.run_started = Some(Instant::now());
            self.state_note = if self.demo {
                String::new()
            } else {
                self.locale.tr("contacting runtime", "正在连接运行时").into()
            };
        }
        self.scroll_up = 0;
        if !running {
            ctl.send(Cmd::Prompt {
                session_id: self.session_id.clone(),
                text,
            });
        }
    }

    pub(crate) fn dispatch_next_queued(&mut self, ctl: &Controller) {
        if self.queue_selection.is_some() || self.queue_edit.is_some() {
            self.state_note = self
                .locale
                .tr("queue paused for selection/edit", "队列已暂停 · 请选择或编辑")
                .into();
            self.show_tip(self.locale.tr(
                "queue paused · finish or close the queue editor",
                "队列暂停 · 完成或关闭队列编辑器",
            ));
            return;
        }
        if !self.session_bound {
            // The tab still awaits (or lost) its session bind: an unbound
            // id would be rejected by acp, and every rejection error would
            // re-enter this function and burn the whole queue. The prompt
            // stays queued for the SessionBound handler (issue #94).
            return;
        }
        let Some(prompt) = self.prompt_queue.pop_front() else {
            return;
        };
        self.queued = self.prompt_queue.len();
        self.echo_staged_blocks(&prompt.blocks);
        self.prompt_pending = true;
        self.state = RunState::Starting;
        self.run_started = Some(Instant::now());
        self.state_note = self.locale.tr("sending queued followup", "正在发送排队消息").into();
        self.scroll_up = 0;

        match prompt.blocks.as_slice() {
            [StagedBlock::Text(text)] => ctl.send(Cmd::Prompt {
                session_id: self.session_id.clone(),
                text: text.clone(),
            }),
            _ => ctl.send(Cmd::PromptImages {
                session_id: self.session_id.clone(),
                blocks: prompt_blocks_from_staged(prompt.blocks),
            }),
        }
    }

    /// Empty Enter promotes the FIFO head into the active turn. If the agent
    /// cannot accept the steer, settlement restores the item to the front.
    pub(crate) fn send_queue_head_now(&mut self, ctl: &Controller) {
        if !self.session_bound {
            self.show_tip(self.locale.tr(
                "session still binding — prompt stays queued",
                "会话仍在绑定中 —— 消息保留在队列里",
            ));
            return;
        }
        if !self.input.is_empty()
            || !self.pending_images.is_empty()
            || self.queue_selection.is_some()
            || self.queue_edit.is_some()
        {
            return;
        }
        let Some(prompt) = self.prompt_queue.pop_front() else {
            return;
        };
        self.queued = self.prompt_queue.len();
        self.show_banner = false;
        self.scroll_up = 0;

        let running = self.state == RunState::Running || self.prompt_pending;
        let message_id = prompt.id;
        let blocks = prompt.blocks;
        let cells = self.echo_staged_blocks(&blocks);
        let text = match blocks.as_slice() {
            [StagedBlock::Text(text)] => Some(text.clone()),
            _ => None,
        };

        if running {
            self.pending_steer_cells.insert(
                message_id,
                PendingSteer {
                    cells,
                    blocks: blocks.clone(),
                    requeue_front: true,
                    gen: self.transcript.gen(),
                },
            );
            self.show_tip(self.locale.tr(
                "queue head sent now — lands at the next agent step",
                "队首已立即发送 —— 在下一步 Agent 处生效",
            ));
            ctl.send(if let Some(text) = text {
                Cmd::Steer {
                    session_id: self.session_id.clone(),
                    message_id,
                    text,
                }
            } else {
                Cmd::SteerImages {
                    session_id: self.session_id.clone(),
                    message_id,
                    blocks: prompt_blocks_from_staged(blocks),
                }
            });
            return;
        }

        self.prompt_pending = true;
        self.state = RunState::Starting;
        self.run_started = Some(Instant::now());
        self.state_note = self.locale.tr("sending queued followup", "正在发送排队消息").into();
        ctl.send(if let Some(text) = text {
            Cmd::Prompt {
                session_id: self.session_id.clone(),
                text,
            }
        } else {
            Cmd::PromptImages {
                session_id: self.session_id.clone(),
                blocks: prompt_blocks_from_staged(blocks),
            }
        });
    }

    pub(crate) fn open_queue_selector(&mut self) {
        if self.queue_selection.is_some() || self.queue_edit.is_some() {
            return;
        }
        if !self.input.is_empty() {
            self.show_tip(self.locale.tr(
                "send or clear the current draft before editing the queue",
                "编辑队列前请先发送或清空当前草稿",
            ));
            return;
        }
        if self.prompt_queue.is_empty() {
            self.show_tip(self.locale.tr("no queued prompt to edit", "没有可编辑的排队消息"));
            return;
        }
        self.queue_selection = Some(self.prompt_queue.len() - 1);
        self.slash_completion_dismissed = true;
        self.show_tip(self.locale.tr(
            "select queued prompt · ↑/↓ choose · enter edit · esc close",
            "选择排队消息 · ↑/↓ 选择 · enter 编辑 · esc 关闭",
        ));
    }

    pub(crate) fn begin_queue_edit_at(&mut self, index: usize) {
        let Some(prompt) = self.prompt_queue.get(index) else {
            self.queue_selection = None;
            self.show_tip(self.locale.tr(
                "queued prompt already left the queue",
                "这条消息已离开队列",
            ));
            return;
        };
        let prompt_id = prompt.id;
        let blocks = prompt.blocks.clone();
        self.queue_selection = None;
        let mut text = String::new();
        for block in blocks {
            match block {
                StagedBlock::Text(block_text) => text.push_str(&block_text),
                StagedBlock::Image(image) => {
                    let token = image.token.clone();
                    if self.pending_images.restore(image).is_ok() {
                        text.push_str(&token);
                    }
                }
            }
        }
        self.queue_edit = Some(QueueEditState {
            prompt_id,
            delete_confirm: false,
        });
        self.input.set(text);
        self.slash_completion_dismissed = false;
        self.show_tip(self.locale.trf(
            "editing queued prompt {} · enter save · ctrl+d delete · esc cancel",
            "编辑排队消息 {} · enter 保存 · ctrl+d 删除 · esc 取消",
            &[(index + 1).to_string()],
        ));
    }

    pub(crate) fn save_queue_edit(&mut self, ctl: &Controller) {
        let Some(edit) = self.queue_edit.as_ref() else {
            return;
        };
        let prompt_id = edit.prompt_id;
        if edit.delete_confirm {
            self.delete_queue_edit(ctl);
            return;
        }
        let raw = self.input.buf().trim().to_string();
        if raw.is_empty() && self.pending_images.is_empty() {
            self.show_tip(self.locale.tr(
                "queued prompt cannot be empty · ctrl+d deletes it",
                "排队消息不能为空 · ctrl+d 可删除",
            ));
            return;
        }
        let blocks = if self.pending_images.is_empty() {
            vec![StagedBlock::Text(raw)]
        } else {
            self.take_staged_blocks()
        };
        let Some(index) = self
            .prompt_queue
            .iter()
            .position(|prompt| prompt.id == prompt_id)
        else {
            self.queue_edit = None;
            self.input.clear();
            self.show_tip(self.locale.tr(
                "queued prompt already left the queue",
                "这条消息已离开队列",
            ));
            return;
        };
        self.prompt_queue[index].blocks = blocks;
        self.queue_edit = None;
        self.input.clear();
        self.slash_completion_dismissed = false;
        self.reconcile_attachments();
        self.show_tip(self.locale.trf(
            "queued prompt {} updated",
            "排队消息 {} 已更新",
            &[(index + 1).to_string()],
        ));
        if matches!(self.state, RunState::Idle) {
            self.dispatch_next_queued(ctl);
        }
    }

    pub(crate) fn delete_queue_edit(&mut self, ctl: &Controller) {
        let Some(prompt_id) = self.queue_edit.as_ref().map(|edit| edit.prompt_id) else {
            return;
        };
        let Some(index) = self
            .prompt_queue
            .iter()
            .position(|prompt| prompt.id == prompt_id)
        else {
            self.queue_edit = None;
            self.input.clear();
            self.show_tip(self.locale.tr(
                "queued prompt already left the queue",
                "这条消息已离开队列",
            ));
            return;
        };
        self.prompt_queue.remove(index);
        self.queued = self.prompt_queue.len();
        self.queue_edit = None;
        self.input.clear();
        self.slash_completion_dismissed = false;
        self.reconcile_attachments();
        self.show_tip(self.locale.trf(
            "queued prompt {} deleted",
            "排队消息 {} 已删除",
            &[(index + 1).to_string()],
        ));
        if matches!(self.state, RunState::Idle) {
            self.dispatch_next_queued(ctl);
        }
    }

    /// `/image <path> [caption]` — stage a local raster in the composer; it is
    /// sent on the next Enter (caption becomes the prompt text).
    pub(crate) fn send_image(&mut self, arg: &str, _ctl: &Controller) {
        let (path, caption) = match arg.split_once(char::is_whitespace) {
            Some((p, rest)) => (p, rest.trim().to_string()),
            None => (arg, String::new()),
        };
        if path.is_empty() {
            self.show_tip(self.locale.tr(
                "/image needs a path — /image ./pic.png [caption]",
                "/image 需要路径 —— /image ./pic.png [说明]",
            ));
            return;
        }
        let Some(media_type) = media_type_for(path) else {
            self.show_tip(self.locale.tr(
                "unsupported image — use .png .jpg .jpeg .webp .gif",
                "不支持的图片 —— 支持 .png .jpg .jpeg .webp .gif",
            ));
            return;
        };
        let bytes = match std::fs::read(path) {
            Ok(b) => b,
            Err(err) => {
                self.show_tip(self.locale.trf(
                    "cannot read {}: {}",
                    "无法读取 {}：{}",
                    &[path.into(), err.to_string()],
                ));
                return;
            }
        };
        let name = path.rsplit('/').next().unwrap_or(path).to_string();
        let stored_path = std::fs::canonicalize(path)
            .or_else(|_| std::path::absolute(path))
            .unwrap_or_else(|_| std::path::PathBuf::from(path))
            .to_string_lossy()
            .into_owned();
        self.stage_image(name, stored_path, media_type.to_string(), bytes, caption);
    }

    /// `/clip [caption]` — stage the clipboard image in the composer.
    pub(crate) fn clip_image(&mut self, caption: &str, _ctl: &Controller) {
        match read_clipboard_image() {
            Some((bytes, media_type)) => self.stage_image(
                "clipboard.png".into(),
                "clipboard".into(),
                media_type.to_string(),
                bytes,
                caption.to_string(),
            ),
            None => self.show_tip(self.locale.tr(
                "clipboard has no image, or this platform isn't supported",
                "剪贴板没有图片，或当前平台不支持",
            )),
        }
    }

    /// Stage an image as an inline `[image N]` chip at the cursor; up to
    /// [`crate::attachments::MAX_STAGED`] ride the next Enter with the text.
    pub(crate) fn stage_image(
        &mut self,
        name: String,
        path: String,
        media_type: String,
        data: Vec<u8>,
        caption: String,
    ) {
        let token = match self.pending_images.add(name, path, media_type, data) {
            Ok(att) => att.token.clone(),
            Err(full) => {
                self.show_tip(if full == "attachment tray is full — send or remove an [image] chip first" {
                    self.locale
                        .tr(full, "附件栏已满 —— 先发送或移除一个 [image] 标记")
                        .to_string()
                } else {
                    full.to_string()
                });
                return;
            }
        };
        self.input_sel = None;
        if !caption.is_empty() {
            self.input.set(caption);
            self.input.insert_char(' ');
        } else if self.input.cursor_char() > 0
            && !self
                .input
                .buf()
                .chars()
                .nth(self.input.cursor_char() - 1)
                .is_none_or(char::is_whitespace)
        {
            self.input.insert_char(' ');
        }
        self.input.insert_str(&token);
        self.show_tip(self.locale.tr(
            "image staged — ⌫ deletes its chip · hover it to preview",
            "图片已附加 —— ⌫ 删除其标记 · 悬停可预览",
        ));
        self.needs_redraw = true;
    }

    /// Drain the tray and split the draft on chip spans, in reading order.
    pub(crate) fn take_staged_blocks(&mut self) -> Vec<StagedBlock> {
        self.reconcile_attachments();
        let buf = self.input.buf();
        split_draft_into_staged_blocks(&buf, self.pending_images.drain())
    }

    pub(crate) fn next_prompt_id(&mut self) -> u64 {
        let id = self.next_prompt_id;
        self.next_prompt_id = self.next_prompt_id.wrapping_add(1).max(1);
        id
    }

    /// Echo staged blocks in the transcript (text and image thumbnails in
    /// draft order) and send one prompt whose ACP blocks match that order.
    pub(crate) fn echo_staged_blocks(&mut self, staged: &[StagedBlock]) -> Vec<usize> {
        let first_cell = self.transcript.cells.len();
        for block in staged {
            match block {
                StagedBlock::Text(text) => self.transcript.push_user(text.clone(), false),
                StagedBlock::Image(att) => self.transcript.push_image(
                    att.name.clone(),
                    String::new(),
                    att.path.clone(),
                    att.data.clone(),
                    false,
                ),
            }
        }
        (first_cell..self.transcript.cells.len()).collect()
    }

    pub(crate) fn emit_staged_prompt(
        &mut self,
        staged: Vec<StagedBlock>,
        steer_message_id: Option<u64>,
        ctl: &Controller,
    ) {
        self.show_banner = false;
        let cells = self.echo_staged_blocks(&staged);
        if let Some(message_id) = steer_message_id {
            self.pending_steer_cells.insert(
                message_id,
                PendingSteer {
                    cells,
                    blocks: staged.clone(),
                    requeue_front: false,
                    gen: self.transcript.gen(),
                },
            );
        }
        self.scroll_up = 0;
        let blocks = prompt_blocks_from_staged(staged);
        ctl.send(if let Some(message_id) = steer_message_id {
            Cmd::SteerImages {
                session_id: self.session_id.clone(),
                message_id,
                blocks,
            }
        } else {
            Cmd::PromptImages {
                session_id: self.session_id.clone(),
                blocks,
            }
        });
    }

    /// Submit path for the staged tray: set run state / queue bookkeeping,
    /// then emit the interleaved prompt.
    pub(crate) fn send_staged(&mut self, staged: Vec<StagedBlock>, ctl: &Controller) {
        if staged.is_empty() {
            return;
        }
        let n = staged
            .iter()
            .filter(|b| matches!(b, StagedBlock::Image(_)))
            .count();
        let running = self.state == RunState::Running || self.prompt_pending || self.queued > 0;
        if running {
            let id = self.next_prompt_id();
            self.prompt_queue
                .push_back(ClientQueuedPrompt { id, blocks: staged });
            self.queued += 1;
            self.show_tip(if n <= 1 {
                self.locale
                    .tr("image queued · empty enter sends first", "图片已排队 · 空输入按 enter 发送队首")
                    .to_string()
            } else {
                self.locale.trf(
                    "{} images queued · empty enter sends first",
                    "{} 张图片已排队 · 空输入按 enter 发送队首",
                    &[n.to_string()],
                )
            });
            self.scroll_up = 0;
            return;
        } else {
            self.prompt_pending = true;
            self.state = RunState::Starting;
            self.run_started = Some(Instant::now());
            self.state_note = if n <= 1 {
                self.locale.tr("sending image", "正在发送图片").into()
            } else {
                self.locale
                    .tr_fmt("sending {} images", "正在发送 {} 张图片", n)
            };
        }
        self.emit_staged_prompt(staged, None, ctl);
    }

    /// Send-now is ACP steering: issue another prompt immediately while the
    /// current turn remains active. Esc is the only cancellation path.
    pub(crate) fn send_now(&mut self, ctl: &Controller) {
        let raw = self.input.buf().trim().to_string();
        if !self.pending_images.is_empty() && (raw.starts_with('/') || raw.starts_with('!')) {
            self.show_tip(
                self.locale.tr(
                    "send or delete the [image] chips first — /commands and !shell don't take images",
                    "先发送或删除 [image] 标记 —— /命令 和 !shell 不接受图片",
                ),
            );
            return;
        }
        let staged = if self.pending_images.is_empty() {
            if raw.is_empty() {
                return;
            }
            vec![StagedBlock::Text(raw)]
        } else {
            self.take_staged_blocks()
        };
        if staged.is_empty() {
            return;
        }
        let running = self.state == RunState::Running || self.prompt_pending || self.queued > 0;
        self.input.history.push(self.input.buf());
        self.input.clear();
        self.show_banner = false;
        let has_images = staged.iter().any(|b| matches!(b, StagedBlock::Image(_)));
        if has_images {
            let n = staged
                .iter()
                .filter(|b| matches!(b, StagedBlock::Image(_)))
                .count();
            if running {
                self.show_tip(self.locale.tr(
                    "steered with image — lands at the next agent step",
                    "已带图 steer —— 在下一步 Agent 处生效",
                ));
            } else {
                self.prompt_pending = true;
                self.state = RunState::Starting;
                self.run_started = Some(Instant::now());
                self.state_note = if n == 1 {
                    self.locale.tr("sending image", "正在发送图片").into()
                } else {
                    self.locale
                        .tr_fmt("sending {} images", "正在发送 {} 张图片", n)
                };
            }
            let steer_message_id = running.then(|| self.next_prompt_id());
            self.emit_staged_prompt(staged, steer_message_id, ctl);
        } else {
            let text = match staged.into_iter().next() {
                Some(StagedBlock::Text(t)) => t,
                _ => return,
            };
            let cell = self.transcript.cells.len();
            self.transcript.push_user(text.clone(), false);
            if running {
                self.show_tip(self.locale.tr(
                    "steered — lands at the next agent step",
                    "已 steer —— 在下一步 Agent 处生效",
                ));
            } else {
                self.prompt_pending = true;
                self.state = RunState::Starting;
                self.run_started = Some(Instant::now());
            }
            self.scroll_up = 0;
            ctl.send(if running {
                let message_id = self.next_prompt_id();
                self.pending_steer_cells.insert(
                    message_id,
                    PendingSteer {
                        cells: vec![cell],
                        blocks: vec![StagedBlock::Text(text.clone())],
                        requeue_front: false,
                        gen: self.transcript.gen(),
                    },
                );
                Cmd::Steer {
                    session_id: self.session_id.clone(),
                    message_id,
                    text,
                }
            } else {
                Cmd::Prompt {
                    session_id: self.session_id.clone(),
                    text,
                }
            });
        }
    }

    /// Submit a prompt programmatically (used by CROW_AUTOPROMPT).
    pub fn auto_prompt(&mut self, text: &str, ctl: &Controller) {
        self.show_banner = false;
        self.input_sel = None;
        self.input.set(text.to_string());
        self.submit(ctl);
    }

    pub(crate) fn run_local_shell(&mut self, cmd: String) {
        self.shell_seq += 1;
        let id = self.shell_seq;
        let cell = self.transcript.push_shell(cmd.clone());
        // Tag the pending cell with its session: the worker is shared and
        // the user may switch tabs before the command settles.
        self.shell_pending.push((id, self.session_id.clone(), cell, self.transcript.gen()));
        let request = ShellRequest { id, command: cmd };
        let worker = self.shell_worker.get_or_insert_with(|| {
            ShellWorker::spawn(self.cfg.workspace.clone(), self.bus_tx.clone())
        });
        if let Err(request) = worker.send(request) {
            let worker = ShellWorker::spawn(self.cfg.workspace.clone(), self.bus_tx.clone());
            if let Err(request) = worker.send(request) {
                let _ = self.bus_tx.send(AppEvent::ShellDone {
                    id: request.id,
                    code: None,
                    output: "failed to start shell worker".into(),
                });
            }
            self.shell_worker = Some(worker);
        }
    }
}
