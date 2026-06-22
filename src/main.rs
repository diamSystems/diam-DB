use axum::{
    routing::{get, post},
    Router,
};
use std::sync::Arc;
use std::path::PathBuf;
use clap::{Parser, Subcommand};

mod state;
mod worker;
mod api;

use state::DbState;

#[derive(Parser)]
#[command(name = "diam-db")]
#[command(about = "A high-performance memory-first NoSQL micro-database", long_about = None)]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Start the database server
    Server {
        /// Host to bind to (default: 127.0.0.1)
        #[arg(long, default_value = "127.0.0.1")]
        host: String,
        /// Port to bind to (default: 8080)
        #[arg(short, long, default_value = "8080")]
        port: u16,
        /// Data directory path (default: ./data)
        #[arg(short, long, default_value = "./data")]
        data_dir: String,
    },
    /// Create a new tenant database
    CreateTenant {
        /// Tenant ID
        tenant_id: String,
        /// Data directory path (default: ./data)
        #[arg(short, long, default_value = "./data")]
        data_dir: String,
    },
}

#[tokio::main]
async fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Server { host, port, data_dir } => {
            let base_path = PathBuf::from(data_dir);
            let state = Arc::new(DbState::init(base_path).await);

            let app = Router::new()
                .route("/health", get(api::health))
                .route("/api/v1/health", get(api::health))
                .route("/api/v1/database/create", post(api::create_tenant))
                .route(
                    "/api/v1/:tenant_id/collection/:collection_name",
                    post(api::write_document).get(api::get_collection),
                )
                .route(
                    "/api/v1/:tenant_id/collection/:collection_name/document/:id",
                    get(api::get_document),
                )
                .route("/api/v1/:tenant_id/stats", get(api::get_tenant_stats))
                .with_state(state);

            let bind_addr = format!("{}:{}", host, port);
            let listener = tokio::net::TcpListener::bind(&bind_addr).await.unwrap();
            println!("diamDB listening on {}", listener.local_addr().unwrap());
            axum::serve(listener, app).await.unwrap();
        }
        Commands::CreateTenant { tenant_id, data_dir } => {
            let base_path = PathBuf::from(data_dir);
            let state = DbState::init(base_path).await;
            state.create_tenant(&tenant_id).await;
            println!("Tenant '{}' created successfully", tenant_id);
        }
    }
}
