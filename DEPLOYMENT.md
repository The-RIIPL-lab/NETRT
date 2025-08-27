# NETRT Deployment Guide

## Docker Deployment (Recommended)

### Prerequisites
- Docker
- Docker Compose
- Network access to source and destination DICOM systems

### Configuration Preparation

1. **Create Configuration File**
   
   Copy and customize `config.yaml`:
   ```yaml
   dicom_listener:
     host: "0.0.0.0"
     port: 11112
     ae_title: "NETRT"
   
   dicom_destination:
     ip: "192.168.1.100"
     port: 104
     ae_title: "DESTINATION"
   ```

2. **Create Data Directories**
   ```bash
   mkdir -p /DATA/netrt_data/working
   mkdir -p /DATA/netrt_data/logs
   ```

### Docker Compose Deployment

The provided `docker compose.yml` file configures the complete environment:

```bash
# Build and start services
docker compose up --build -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Docker Run (Alternative)

```bash
docker build -t netrt-app .

docker run -d \
  --name netrt-instance \
  -p 11112:11112/tcp \
  -v ./config.yaml:/app/config/config.yaml:ro \
  -v /DATA/netrt_data/working:/home/appuser/CNCT_working \
  -v /DATA/netrt_data/logs:/home/appuser/CNCT_logs \
  --restart unless-stopped \
  netrt-app
```

**Volume Mapping**:
- Configuration: Host config → `/app/config/config.yaml`
- Working data: Host path → `/home/appuser/CNCT_working`
- Logs: Host path → `/home/appuser/CNCT_logs`

### Container Management

**View Status**:
```bash
docker compose ps
```

**Access Logs**:
```bash
# Container logs
docker compose logs -f

# Application logs (if volume mounted)
tail -f /DATA/netrt_data/logs/application.log
tail -f /DATA/netrt_data/logs/transaction.log
```

**Restart Service**:
```bash
docker compose restart
```

## Systemd Deployment (Linux Hosts)

### Prerequisites

1. **Install Python Dependencies**
   ```bash
   cd /opt/netrt
   pip install -r requirements.txt
   ```

2. **Create Service User**
   ```bash
   sudo groupadd netrt
   sudo useradd --system --no-create-home -g netrt appuser
   ```

3. **Prepare Directories**
   ```bash
   sudo mkdir -p /var/log/netrt /var/lib/netrt/working
   sudo chown -R appuser:netrt /var/log/netrt /var/lib/netrt
   ```

### Service Configuration

1. **Copy Unit File**
   ```bash
   sudo cp netrt.service.example /etc/systemd/system/netrt.service
   ```

2. **Edit Unit File** (`/etc/systemd/system/netrt.service`):
   ```ini
   [Unit]
   Description=NETRT DICOM Processing Application
   After=network.target
   
   [Service]
   Type=simple
   User=appuser
   Group=netrt
   WorkingDirectory=/opt/netrt
   ExecStart=/usr/bin/python3 /opt/netrt/main.py --config /etc/netrt/config.yaml
   Restart=on-failure
   RestartSec=5s
   StandardOutput=journal
   StandardError=journal
   
   [Install]
   WantedBy=multi-user.target
   ```

3. **Install and Start**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable netrt.service
   sudo systemctl start netrt.service
   ```

4. **Monitor Service**
   ```bash
   sudo systemctl status netrt.service
   sudo journalctl -u netrt.service -f
   ```

## Network Configuration

### DICOM Network Setup

**Listener Configuration**:
- Bind to specific interface for security
- Use non-privileged ports (> 1024) when possible
- Configure appropriate AE Title for identification

**Destination Configuration**:
- Verify network connectivity: `telnet <destination_ip> <port>`
- Confirm AE Title with destination system administrator
- Test with DICOM echo: `echoscu <destination_ip> <port> -aet <your_aet> -aec <dest_aet>`

### Firewall Rules

**Allow Incoming DICOM**:
```bash
# Ubuntu/Debian
sudo ufw allow from <source_network> to any port <netrt_port>

# RHEL/CentOS
sudo firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='<source_network>' port protocol='tcp' port='<netrt_port>' accept"
sudo firewall-cmd --reload
```

**Allow Outgoing DICOM**:
```bash
# Usually allowed by default, but verify if restrictive policies
sudo ufw allow out <destination_port>
```

## Monitoring and Maintenance

### Log Management

**Docker Environment**:
```bash
# View recent application events
docker compose exec netrt tail -f /home/appuser/CNCT_logs/application.log

# Monitor transactions
docker compose exec netrt tail -f /home/appuser/CNCT_logs/transaction.log
```

**Systemd Environment**:
```bash
# System logs
sudo journalctl -u netrt.service --since today

# Application logs
sudo tail -f /var/log/netrt/application.log
sudo tail -f /var/log/netrt/transaction.log
```

### Health Monitoring

**DICOM Connectivity Test**:
```bash
# Test C-ECHO to NETRT
echoscu <netrt_host> <netrt_port> -aet TEST -aec <netrt_aet>

# Test connectivity to destination
echoscu <dest_host> <dest_port> -aet <netrt_aet> -aec <dest_aet>
```

**Storage Monitoring**:
```bash
# Check working directory usage
du -sh /DATA/netrt_data/working

# Monitor quarantine directory
ls -la /DATA/netrt_data/working/quarantine
```

### Maintenance Tasks

**Update Application**:
```bash
# Docker deployment
docker compose down
docker compose pull
docker compose up --build -d

# Systemd deployment
sudo systemctl stop netrt.service
# Update application files
sudo systemctl start netrt.service
```

**Clean Quarantine Directory**:
```bash
# Review quarantined studies
ls -la /DATA/netrt_data/working/quarantine

# Remove after analysis (be cautious)
sudo rm -rf /DATA/netrt_data/working/quarantine/UID_<specific_study>
```

## Production Considerations

### Resource Requirements
- **CPU**: 2+ cores for concurrent processing
- **Memory**: 4GB+ RAM for large studies
- **Storage**: 10GB+ for temporary processing, plus log retention
- **Network**: Stable connectivity to source and destination systems

### Security Hardening
- Run containers with non-root user (already configured)
- Use specific network interfaces instead of 0.0.0.0 when possible
- Implement network segmentation for DICOM traffic
- Regular security updates for base images and system packages

### Backup and Recovery
- Configuration files: Include in regular backup procedures
- Logs: Implement log rotation and archival
- Quarantine data: Backup before cleanup for compliance
- No patient data persistence: Working directory can be cleared safely

### Scalability Options
- Multiple instances with different AE Titles for load distribution
- External storage volumes for high-throughput environments
- Container orchestration (Kubernetes) for enterprise deployments