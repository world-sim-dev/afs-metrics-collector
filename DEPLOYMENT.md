# AFS Prometheus Metrics Collector - Deployment Guide

This guide covers different deployment options for the AFS Prometheus Metrics Collector.

## Docker Deployment

### Quick Start with Docker

1. **Build the Docker image:**
   ```bash
   ./docker-build.sh
   ```

2. **Create environment file:**
   ```bash
   cp .env.example .env
   # Edit .env with your AFS credentials
   ```

3. **Run with Docker:**
   ```bash
   docker run -d -p 8080:8080 --env-file .env afs-prometheus-metrics:latest
   ```

### Docker Compose Deployment

1. **Create environment file:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Build and run:**
   ```bash
   # Build the image
   docker build -t afs-metrics-collector .
   
   # Run the container
   docker run -d --name afs-metrics -p 8080:8080 \
     --env-file .env \
     afs-metrics-collector
   ```

3. **View logs:**
   ```bash
   docker logs -f afs-metrics
   ```

### Docker Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AFS_ACCESS_KEY` | AFS API access key | Required |
| `AFS_SECRET_KEY` | AFS API secret key | Required |
| `AFS_BASE_URL` | AFS API base URL | `https://afs.cn-sh-01.sensecoreapi.cn` |
| `SERVER_HOST` | Server bind address | `0.0.0.0` |
| `SERVER_PORT` | Server port | `8080` |
| `REQUEST_TIMEOUT` | HTTP request timeout | `30` |
| `COLLECTION_TIMEOUT` | Collection timeout | `25` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Configuration

### Environment Variables Configuration

Set these environment variables or include them in your `.env` file:

```bash
# Required
AFS_ACCESS_KEY=your_access_key
AFS_SECRET_KEY=your_secret_key

# Optional
AFS_BASE_URL=https://afs.cn-sh-01.sensecoreapi.cn
AFS_VOLUMES='[{"volume_id": "01987d8c-2d13-78cc-ba7b-1ad9beb7e552", "zone": "cn-sh-01e"}]'

SERVER_HOST=0.0.0.0
SERVER_PORT=8080
REQUEST_TIMEOUT=30

COLLECTION_TIMEOUT=25
COLLECTION_MAX_RETRIES=3
COLLECTION_RETRY_DELAY=2
COLLECTION_CACHE_DURATION=30

LOG_LEVEL=INFO
LOG_FORMAT=json
```

### YAML Configuration File

Alternatively, create a `config.yaml` file:

```yaml
afs:
  access_key: "your_access_key"
  secret_key: "your_secret_key"
  base_url: "https://afs.cn-sh-01.sensecoreapi.cn"
  volumes:
    - volume_id: "01987d8c-2d13-78cc-ba7b-1ad9beb7e552"
      zone: "cn-sh-01e"

server:
  host: "0.0.0.0"
  port: 8080
  request_timeout: 30

collection:
  timeout_seconds: 25
  max_retries: 3
  retry_delay: 2
  cache_duration: 30

logging:
  level: "INFO"
  format: "json"
```

## Prometheus Integration

### Prometheus Configuration

Add this job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'afs-storage'
    static_configs:
      - targets: ['your-server:8080']
    scrape_interval: 60s
    scrape_timeout: 30s
    metrics_path: /metrics
```

### Available Endpoints

- **Metrics:** `GET /metrics` - Prometheus metrics endpoint
- **Health (Live):** `GET /health/live` - Liveness probe
- **Health (Ready):** `GET /health/ready` - Readiness probe

### Sample Metrics

```
# HELP afs_capacity_used_bytes Used storage capacity in bytes
# TYPE afs_capacity_used_bytes gauge
afs_capacity_used_bytes{volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e",dir_path="/datasets"} 21643634736022

# HELP afs_capacity_quota_bytes Total capacity quota in bytes (0 means unlimited)
# TYPE afs_capacity_quota_bytes gauge
afs_capacity_quota_bytes{volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e",dir_path="/datasets"} 0

# HELP afs_file_quantity_used Number of files used
# TYPE afs_file_quantity_used gauge
afs_file_quantity_used{volume_id="80433778-429e-11ef-bc97-4eca24dcdba9",zone="cn-sh-01e",dir_path="/datasets"} 26351937
```

## Monitoring and Troubleshooting

### Health Checks

```bash
# Check if service is running
curl http://localhost:8080/health/live

# Check if service is ready
curl http://localhost:8080/health/ready

# Get metrics
curl http://localhost:8080/metrics
```

### Common Issues

1. **Authentication Errors:**
   - Verify AFS credentials are correct
   - Check if credentials have proper permissions

2. **Connection Timeouts:**
   - Increase `COLLECTION_TIMEOUT` value
   - Check network connectivity to AFS API

3. **Service Won't Start:**
   - Check configuration with `--validate-config`
   - Review Docker logs with `docker logs <container_name>`

### Logging

Logs are available through:
- **Docker:** `docker logs <container_name>`

## Security Considerations

1. **Credentials:** Store AFS credentials securely (environment variables, secrets management)
2. **Network:** Use TLS/HTTPS for production deployments
3. **User Permissions:** Service runs as non-root user `afs-collector`
4. **File Permissions:** Configuration files have restricted permissions (600)

## Performance Tuning

1. **Cache Duration:** Adjust `COLLECTION_CACHE_DURATION` based on scrape frequency
2. **Timeouts:** Tune `COLLECTION_TIMEOUT` and `REQUEST_TIMEOUT` for your environment
3. **Retries:** Configure `COLLECTION_MAX_RETRIES` and `COLLECTION_RETRY_DELAY`
4. **Resource Limits:** Set appropriate memory limits in Docker