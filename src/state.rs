use dashmap::DashMap;
use serde_json::Value;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::fs;
use tokio::sync::{mpsc, RwLock};
use crate::worker::spawn_tenant_worker;

pub type CollectionData = HashMap<String, Value>;
pub type TenantData = HashMap<String, CollectionData>;

#[derive(Debug)]
pub enum TransactionEvent {
    Write {
        collection: String,
        document_id: String,
        payload: Value,
    },
}

pub struct Tenant {
    pub id: String,
    pub data: Arc<RwLock<TenantData>>,
    pub tx: mpsc::Sender<TransactionEvent>,
}

pub struct DbState {
    pub tenants: DashMap<String, Arc<Tenant>>,
    pub base_path: PathBuf,
}

impl DbState {
    pub async fn init(base_path: PathBuf) -> Self {
        fs::create_dir_all(&base_path).await.unwrap();
        let state = Self {
            tenants: DashMap::new(),
            base_path,
        };
        let _ = state.load_all_tenants().await;
        state
    }

    async fn load_all_tenants(&self) -> std::io::Result<()> {
        let mut dir = match fs::read_dir(&self.base_path).await {
            Ok(dir) => dir,
            Err(_) => return Ok(()),
        };

        while let Some(entry) = dir.next_entry().await? {
            if entry.file_type().await?.is_dir() {
                let tenant_id = entry.file_name().into_string().unwrap();
                let tenant_dir = self.base_path.join(&tenant_id);

                let mut tenant_data: TenantData = HashMap::new();

                // 1. Load data.json
                let data_path = tenant_dir.join("data.json");
                if data_path.exists() {
                    if let Ok(content) = fs::read_to_string(&data_path).await {
                        if let Ok(parsed) = serde_json::from_str(&content) {
                            tenant_data = parsed;
                        }
                    }
                }

                // 2. Load and replay transactions.log
                let log_path = tenant_dir.join("transactions.log");
                if log_path.exists() {
                    if let Ok(content) = fs::read_to_string(&log_path).await {
                        for line in content.lines() {
                            if line.trim().is_empty() {
                                continue;
                            }
                            if let Ok(entry) = serde_json::from_str::<Value>(line) {
                                if entry["type"] == "write" {
                                    if let (Some(col), Some(id), Some(payload)) = (
                                        entry["collection"].as_str(),
                                        entry["document_id"].as_str(),
                                        entry.get("payload"),
                                    ) {
                                        let col_map = tenant_data.entry(col.to_string()).or_default();
                                        col_map.insert(id.to_string(), payload.clone());
                                    }
                                }
                            }
                        }
                    }
                }

                let data = Arc::new(RwLock::new(tenant_data));
                let (tx, rx) = mpsc::channel(1024);

                tokio::spawn(spawn_tenant_worker(
                    tenant_id.clone(),
                    self.base_path.clone(),
                    data.clone(),
                    rx,
                ));

                let tenant = Arc::new(Tenant {
                    id: tenant_id.clone(),
                    data,
                    tx,
                });
                self.tenants.insert(tenant_id, tenant);
            }
        }
        Ok(())
    }

    pub async fn create_tenant(&self, tenant_id: &str) {
        if self.tenants.contains_key(tenant_id) {
            println!("Tenant '{}' already exists", tenant_id);
            return;
        }

        let tenant_dir = self.base_path.join(tenant_id);
        fs::create_dir_all(&tenant_dir).await.unwrap();

        let data: TenantData = HashMap::new();
        let data = Arc::new(RwLock::new(data));
        let (tx, rx) = mpsc::channel(1024);

        tokio::spawn(spawn_tenant_worker(
            tenant_id.to_string(),
            self.base_path.clone(),
            data.clone(),
            rx,
        ));

        let tenant = Arc::new(Tenant {
            id: tenant_id.to_string(),
            data,
            tx,
        });
        self.tenants.insert(tenant_id.to_string(), tenant);
    }
}
