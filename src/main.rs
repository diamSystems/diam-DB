use axum::{
    routing::{get, post},
    Router,
};
use std::sync::Arc;
use std::path::PathBuf;

mod state;
mod worker;
mod api;

use state::DbState;

#[tokio::main]
async fn main() {
    let base_path = PathBuf::from("./data");
    let state = Arc::new(DbState::init(base_path).await);

    let app = Router::new()
        .route("/api/v1/database/create", post(api::create_tenant))
        .route(
            "/api/v1/:tenant_id/collection/:collection_name",
            post(api::write_document).get(api::get_collection),
        )
        .route(
            "/api/v1/:tenant_id/collection/:collection_name/document/:id",
            get(api::get_document),
        )
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("127.0.0.1:8080").await.unwrap();
    println!("diamDB listening on {}", listener.local_addr().unwrap());
    axum::serve(listener, app).await.unwrap();
}
