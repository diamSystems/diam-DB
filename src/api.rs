use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::Deserialize;
use serde_json::Value;
use std::sync::Arc;
use uuid::Uuid;
use std::collections::HashMap;

use crate::state::{DbState, Tenant, TransactionEvent};
use crate::worker::spawn_tenant_worker;
use tokio::sync::{mpsc, RwLock};

#[derive(Deserialize)]
pub struct CreateTenantRequest {
    pub tenant_id: String,
}

pub async fn create_tenant(
    State(state): State<Arc<DbState>>,
    Json(payload): Json<CreateTenantRequest>,
) -> impl IntoResponse {
    let tenant_id = payload.tenant_id;
    if state.tenants.contains_key(&tenant_id) {
        return (StatusCode::CONFLICT, "Tenant already exists").into_response();
    }

    let data = Arc::new(RwLock::new(HashMap::new()));
    let (tx, rx) = mpsc::channel(1024);

    tokio::spawn(spawn_tenant_worker(
        tenant_id.clone(),
        state.base_path.clone(),
        data.clone(),
        rx,
    ));

    let tenant = Arc::new(Tenant {
        id: tenant_id.clone(),
        data,
        tx,
    });

    state.tenants.insert(tenant_id, tenant);

    (StatusCode::CREATED, "Tenant created").into_response()
}

pub async fn write_document(
    State(state): State<Arc<DbState>>,
    Path((tenant_id, collection_name)): Path<(String, String)>,
    Json(mut payload): Json<Value>,
) -> impl IntoResponse {
    let tenant = match state.tenants.get(&tenant_id) {
        Some(t) => t.clone(),
        None => return (StatusCode::NOT_FOUND, "Tenant not found").into_response(),
    };

    let document_id = if let Some(id) = payload.get("id").and_then(|v| v.as_str()) {
        id.to_string()
    } else {
        let new_id = Uuid::new_v4().to_string();
        if let Some(obj) = payload.as_object_mut() {
            obj.insert("id".to_string(), Value::String(new_id.clone()));
        }
        new_id
    };

    // Update in-memory cache instantly
    {
        let mut write_lock = tenant.data.write().await;
        let collection = write_lock.entry(collection_name.clone()).or_default();
        collection.insert(document_id.clone(), payload.clone());
    }

    // Queue to transactions log
    let event = TransactionEvent::Write {
        collection: collection_name,
        document_id,
        payload,
    };

    if tenant.tx.send(event).await.is_err() {
        return (StatusCode::INTERNAL_SERVER_ERROR, "Worker channel closed").into_response();
    }

    (StatusCode::OK, "Document written").into_response()
}

pub async fn get_collection(
    State(state): State<Arc<DbState>>,
    Path((tenant_id, collection_name)): Path<(String, String)>,
) -> impl IntoResponse {
    let tenant = match state.tenants.get(&tenant_id) {
        Some(t) => t.clone(),
        None => return (StatusCode::NOT_FOUND, "Tenant not found").into_response(),
    };

    let read_lock = tenant.data.read().await;
    match read_lock.get(&collection_name) {
        Some(collection) => (StatusCode::OK, Json(collection.clone())).into_response(),
        None => (StatusCode::OK, Json(serde_json::json!({}))).into_response(),
    }
}

pub async fn get_document(
    State(state): State<Arc<DbState>>,
    Path((tenant_id, collection_name, document_id)): Path<(String, String, String)>,
) -> impl IntoResponse {
    let tenant = match state.tenants.get(&tenant_id) {
        Some(t) => t.clone(),
        None => return (StatusCode::NOT_FOUND, "Tenant not found").into_response(),
    };

    let read_lock = tenant.data.read().await;
    match read_lock.get(&collection_name).and_then(|c| c.get(&document_id)) {
        Some(doc) => (StatusCode::OK, Json(doc.clone())).into_response(),
        None => (StatusCode::NOT_FOUND, "Document not found").into_response(),
    }
}
