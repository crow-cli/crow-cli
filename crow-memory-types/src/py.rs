//! Python bindings for the wire types (cargo feature = "python").
//!
//! Every wire type becomes a Python class whose (de)serialization goes
//! through the SAME serde impls the crow-memory server uses — one contract,
//! zero codegen. Construction is only via `from_dict` / `from_json`, both of
//! which run the wire's serde validation; invalid data raises `ValueError`
//! with the serde error. Built into a wheel by maturin (see ../pyproject.toml).

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pythonize::{depythonize, pythonize};

fn ser_err(e: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(e.to_string())
}

macro_rules! pytype {
    ($name:ident { $($field:ident),* $(,)? }) => {
        #[pyclass]
        pub struct $name {
            inner: crate::$name,
        }

        #[pymethods]
        impl $name {
            /// Parse from a Python dict through the wire serde impl.
            #[staticmethod]
            fn from_dict(obj: Bound<'_, PyAny>) -> PyResult<Self> {
                let inner: crate::$name = depythonize(&obj).map_err(ser_err)?;
                Ok(Self { inner })
            }

            /// Parse from a JSON string through the wire serde impl.
            #[staticmethod]
            fn from_json(s: &str) -> PyResult<Self> {
                let inner: crate::$name = serde_json::from_str(s).map_err(ser_err)?;
                Ok(Self { inner })
            }

            /// Serialize to a Python dict through the wire serde impl.
            fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
                Ok(pythonize(py, &self.inner)?)
            }

            /// Serialize to a JSON string through the wire serde impl.
            fn to_json(&self) -> PyResult<String> {
                serde_json::to_string(&self.inner).map_err(ser_err)
            }

            fn __repr__(&self) -> String {
                format!(
                    "{}({})",
                    stringify!($name),
                    serde_json::to_string(&self.inner).unwrap_or_default()
                )
            }

            $(
                #[getter]
                fn $field<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
                    Ok(pythonize(py, &self.inner.$field)?)
                }
            )*
        }
    };
}

pytype!(PromptRecord { id, name, template });
pytype!(AgentRecord {
    agent_id,
    session_id,
    agent_idx,
    cwd,
    prompt_id,
    prompt_args,
    system_prompt,
    tool_definitions,
    request_params,
    model_identifier,
    status,
    created_at
});
pytype!(MessageRecord { id, agent_id, created_at, data, role, score });
pytype!(SessionInfo {
    session_id,
    last_activity,
    message_count,
    agent_count,
    last_role,
    cwd,
    model_identifier,
    agent_idxs,
    last_message
});
pytype!(LookupPromptRequest { template, name });
pytype!(LookupPromptResponse { prompt_id });
pytype!(CreateAgentRequest {
    agent_id,
    session_id,
    agent_idx,
    cwd,
    prompt_id,
    prompt_args,
    system_prompt,
    tool_definitions,
    request_params,
    model_identifier
});
pytype!(AddMessageRequest { agent_id, message, usage });
pytype!(AddMessageResponse { id });
pytype!(SearchMessagesRequest { query, limit, role });
pytype!(MaxAgentIdxResponse { max_idx });
pytype!(ErrorResponse { error });
pytype!(AddImageRequest { mime, data, w, h });
pytype!(ImageRecord { image_id, mime, data, w, h, created_at });

#[pymodule]
pub fn crow_memory_types(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PromptRecord>()?;
    m.add_class::<AgentRecord>()?;
    m.add_class::<MessageRecord>()?;
    m.add_class::<SessionInfo>()?;
    m.add_class::<LookupPromptRequest>()?;
    m.add_class::<LookupPromptResponse>()?;
    m.add_class::<CreateAgentRequest>()?;
    m.add_class::<AddMessageRequest>()?;
    m.add_class::<AddMessageResponse>()?;
    m.add_class::<SearchMessagesRequest>()?;
    m.add_class::<MaxAgentIdxResponse>()?;
    m.add_class::<ErrorResponse>()?;
    m.add_class::<AddImageRequest>()?;
    m.add_class::<ImageRecord>()?;
    m.add("DEFAULT_MEMORY_PORT", crate::DEFAULT_MEMORY_PORT)?;
    m.add(
        "SCHEMA_JSON",
        serde_json::to_string_pretty(&crate::wire_schema()).map_err(ser_err)?,
    )?;
    Ok(())
}
