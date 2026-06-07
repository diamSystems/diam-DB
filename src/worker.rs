use crate::state::{TenantData, TransactionEvent};
use serde_json::json;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::fs::{self, OpenOptions};
use tokio::io::AsyncWriteExt;
use tokio::sync::{mpsc, RwLock};
use tokio::time::{self, Duration};

pub async fn spawn_tenant_worker(
    tenant_id: String,
    base_path: PathBuf,
    data: Arc<RwLock<TenantData>>,
    mut rx: mpsc::Receiver<TransactionEvent>,
) {
    let tenant_dir = base_path.join(&tenant_id);
    let log_path = tenant_dir.join("transactions.log");
    let data_path = tenant_dir.join("data.json");
    let tmp_data_path = tenant_dir.join("data.tmp");

    // Ensure directory exists
    let _ = fs::create_dir_all(&tenant_dir).await;

    // Open log file for appending
    let mut log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .await
        .expect("Failed to open transactions.log");

    let mut ops_since_compact = 0;
    let compact_threshold = 100; // compact after 100 ops
    let mut interval = time::interval(Duration::from_secs(60));

    loop {
        tokio::select! {
            Some(event) = rx.recv() => {
                match event {
                    TransactionEvent::Write { collection, document_id, payload } => {
                        let entry = json!({
                            "type": "write",
                            "collection": collection,
                            "document_id": document_id,
                            "payload": payload,
                        });
                        
                        let mut line = serde_json::to_string(&entry).unwrap();
                        line.push('\n');
                        
                        // Append to log and flush
                        if let Err(e) = log_file.write_all(line.as_bytes()).await {
                            eprintln!("Failed to write to log for tenant {}: {}", tenant_id, e);
                        }

                        ops_since_compact += 1;
                        if ops_since_compact >= compact_threshold {
                            ops_since_compact = 0;
                            compact_data(&data, &data_path, &tmp_data_path, &log_path, &mut log_file).await;
                        }
                    }
                }
            }
            _ = interval.tick() => {
                if ops_since_compact > 0 {
                    ops_since_compact = 0;
                    compact_data(&data, &data_path, &tmp_data_path, &log_path, &mut log_file).await;
                }
            }
            else => break, // Channel closed
        }
    }
}

async fn compact_data(
    data: &Arc<RwLock<TenantData>>,
    data_path: &Path,
    tmp_path: &Path,
    log_path: &Path,
    log_file: &mut tokio::fs::File,
) {
    let current_data = {
        let lock = data.read().await;
        serde_json::to_vec(&*lock).unwrap()
    };

    // Atomically write data.json
    if fs::write(tmp_path, current_data).await.is_ok() {
        if fs::rename(tmp_path, data_path).await.is_ok() {
            // Truncate the log file since we successfully compacted
            if let Ok(new_log) = OpenOptions::new().create(true).write(true).truncate(true).open(log_path).await {
                *log_file = new_log;
            }
        }
    }
}
