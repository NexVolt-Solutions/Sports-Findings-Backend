# Docker Quick Reference - Sports Platform

## 📦 Quick Start

### Development
```bash
# Start all services with hot-reload
docker-compose -f docker-compose.dev.yml up -d

# Adminer UI: http://localhost:8080
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

### Production
```bash
# Start production environment
docker-compose up -d

# Verify health
curl http://localhost:8000/health
```

---

## 🛠️ Common Commands

### Container Management
```bash
# List running containers
docker-compose ps

# View real-time logs
docker-compose logs -f api

# View last 50 lines
docker-compose logs api --tail 50

# Execute command in container
docker-compose exec api python -c "print('hello')"

# Restart service
docker-compose restart api

# Stop all services
docker-compose down

# Stop with volume cleanup
docker-compose down -v
```

### Build & Deploy
```bash
# Build images
docker-compose build

# Build without cache
docker-compose build --no-cache

# View image sizes
docker images | grep sports

# Tag image for registry
docker tag sports-platform-api:latest myregistry.azurecr.io/sports-platform-api:v1.0.0
```

### Database
```bash
# Access database CLI
docker-compose exec db psql -U postgres -d sports_platform

# Run migrations
docker-compose exec api alembic upgrade head

# Check migration status
docker-compose exec api alembic current

# Backup database
docker-compose exec db pg_dump -U postgres sports_platform > backup.sql

# Restore database
docker-compose exec db psql -U postgres sports_platform < backup.sql
```

### Monitoring
```bash
# Real-time resource usage
docker stats

# Container details
docker-compose inspect api

# Network details
docker network inspect sports-network

# Volume details
docker volume inspect sports_platform_postgres_data
```

---

## 🔧 Configuration

### Environment Variables

**Required for Production:**
```bash
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db:5432/sports_platform
REDIS_URL=redis://:PASSWORD@redis:6379/0
SECRET_KEY=<32-char-hex-key>
DEBUG=False
ENVIRONMENT=production

# External services
GOOGLE_CLIENT_ID=your_id
GOOGLE_CLIENT_SECRET=your_secret
GOOGLE_MAPS_API_KEY=your_key
CLOUDINARY_CLOUD_NAME=your_name
CLOUDINARY_API_KEY=your_key
CLOUDINARY_API_SECRET=your_secret
```

### File Locations

```
sports_platform/
├── Dockerfile              # Production image
├── docker-compose.yml      # Production orchestration
├── docker-compose.dev.yml  # Development setup
├── .dockerignore          # Build context exclusions
├── nginx.conf             # Reverse proxy config
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
└── .env.production       # Production secrets (not in git)
```

---

## 📊 Performance

### Resource Limits (Production)

**API Service:**
```
CPU Limit: 1 core
CPU Reserved: 0.5 cores
Memory Limit: 512MB
Memory Reserved: 256MB
Workers: Calculated as (2 * CPU_cores + 1)
```

**PostgreSQL:**
```
CPU Limit: 2 cores
Memory Limit: 1GB
Max Connections: 200
```

**Redis:**
```
CPU Limit: 0.5 cores
Memory Limit: 256MB
```

### Tuning Commands

```bash
# Check actual resource usage
docker stats

# Adjust limits in docker-compose.yml
# deploy:
#   resources:
#     limits:
#       cpus: '1'
#       memory: 512M

# Recalculate worker count
# Workers = 2 * nproc + 1 = 2 * 4 + 1 = 9 (for 4-core CPU)
```

---

## 🔒 Security

### Secrets Management

```bash
# Generate secret key
openssl rand -hex 32

# Never commit .env.production
echo ".env.production" >> .gitignore

# Use secure vault (AWS Secrets Manager, HashiCorp Vault, etc.)

# Verify secrets are set
docker-compose config | grep SECRET_KEY
```

### SSL/TLS

```bash
# Generate Let's Encrypt certificate
sudo certbot certonly --standalone -d yourdomain.com

# Copy to server
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/key.pem

# Set permissions
sudo chmod 644 ssl/cert.pem ssl/key.pem
```

### Health Check

```bash
# Manual health check
curl -i http://localhost:8000/health

# Expected response: 200 OK with JSON
{
  "status": "healthy",
  "app": "Sports Platform",
  "version": "1.0.0",
  "environment": "production"
}
```

---

## 🐛 Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose logs api

# Check syntax
docker-compose config

# Rebuild image
docker-compose build --no-cache api

# Increase startup time
# In docker-compose.yml: start_period: 30s
```

### Port Already in Use
```bash
# Find process using port
lsof -i :8000

# Kill process or use different port
docker-compose -p alternate_port up -d
```

### Database Connection Failed
```bash
# Check database status
docker-compose ps db

# Check database logs
docker-compose logs db

# Wait longer for startup
docker-compose down && docker-compose up -d
sleep 30

# Test connection
docker-compose exec api python -c \
  "from app.database import engine; print('OK')"
```

### High Memory Usage
```bash
# Check which service is consuming memory
docker stats

# Check API logs for memory leaks
docker-compose logs api | grep -i memory

# Restart service
docker-compose restart api

# Increase memory limit in docker-compose.yml
```

### Disk Space Issues
```bash
# Check disk usage
df -h

# Find large images
docker images --format "{{.Repository}} {{.Size}}"

# Clean up unused resources
docker system prune -a

# Remove specific volume
docker volume rm sports_platform_postgres_data
```

---

## 📈 Scaling

### Horizontal Scaling (Multiple Instances)

```bash
# Start 3 API instances
docker-compose up -d --scale api=3

# Update Nginx upstream
upstream api_backend {
    least_conn;
    server api:8000;
    server api:8001;
    server api:8002;
}

# Reload Nginx
docker-compose exec nginx nginx -s reload
```

### Vertical Scaling (More Resources)

```yaml
# In docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '2'           # Increase from 1
      memory: 1G          # Increase from 512M
    reservations:
      cpus: '1'
      memory: 512M
```

---

## 📝 Logging

### View Logs
```bash
# Real-time (follow mode)
docker-compose logs -f api

# Specific number of lines
docker-compose logs api --tail 100

# Only errors
docker-compose logs api | grep ERROR

# With timestamps
docker-compose logs -t api
```

### Log Configuration
```yaml
# In docker-compose.yml
logging:
  driver: "json-file"
  options:
    max-size: "10m"     # 10MB per file
    max-file: "3"       # Keep 3 files
    labels: "service=api"
```

### Log Rotation
```bash
# Check current log size
du -sh /var/lib/docker/containers/**/

# Setup logrotate (Linux)
sudo cat > /etc/logrotate.d/docker-compose <<EOF
/var/lib/docker/containers/*/*.log {
  rotate 7
  daily
  compress
  delaycompress
}
EOF
```

---

## 🚀 Deployment

### Pre-Deployment Checklist
```bash
# Test build
docker-compose build

# Run tests
docker-compose run api pytest tests/

# Check security
docker scan sports-platform-api:latest

# Validate compose file
docker-compose config

# Load test
docker run --rm -i grafana/k6 run - < loadtest.js
```

### Deploy Steps
```bash
# 1. Pull latest code
git pull origin main

# 2. Backup database
docker-compose exec db pg_dump -U postgres sports_platform > backup.sql

# 3. Build and start
docker-compose up -d --build

# 4. Run migrations
docker-compose exec api alembic upgrade head

# 5. Verify health
docker-compose ps
curl http://localhost:8000/health

# 6. Monitor logs
docker-compose logs -f api
```

### Rollback
```bash
# Stop current deployment
docker-compose down

# Revert to previous version
git checkout PREVIOUS_COMMIT

# Rebuild and start
docker-compose build
docker-compose up -d

# Rollback database if needed
docker-compose exec api alembic downgrade -1

# Verify
curl http://localhost:8000/health
```

---

## 📚 Documentation

- Full setup guide: `DOCKER_SETUP.md`
- Deployment checklist: `DEPLOYMENT_CHECKLIST.md`
- Configuration review: `DOCKER_REVIEW.md`
- App configuration: `app/config.py`
- Main app: `app/main.py`

---

## 🆘 Get Help

```bash
# Docker help
docker-compose --help

# Compose file validation
docker-compose config

# Container inspection
docker inspect <container_id>

# Network inspection
docker network inspect sports-network

# Log aggregation services
# - ELK Stack
# - DataDog
# - New Relic
# - CloudWatch
```

---

## 💡 Pro Tips

1. **Use named volumes** - Persist data even after container deletion
2. **Set resource limits** - Prevent services from consuming all resources
3. **Health checks** - Automatic monitoring and recovery
4. **Environment variables** - Keep secrets out of code
5. **Logging to stdout** - Easier for log aggregation services
6. **Multi-stage builds** - Smaller production images
7. **Run as non-root** - Better security
8. **Regular backups** - Prevent data loss
9. **Test rollbacks** - Practice disaster recovery
10. **Monitor metrics** - Detect issues early

---

Last Updated: 2026-04-02
