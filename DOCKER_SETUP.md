# Docker Setup Guide - Sports Platform

## Overview

This project uses Docker for containerized deployment with three configurations:
- **Development** - Hot-reload with Adminer UI
- **Production** - Optimized for performance and security
- **Local** - Quick setup for testing

---

## Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose)
- Docker Compose v2.0+
- `.env` file configured (copy from `.env.example`)

---

## Development Setup

### Quick Start

```bash
# Start development environment with hot-reload
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f api

# Stop services
docker-compose -f docker-compose.dev.yml down
```

### What's Included

- **API** - FastAPI with auto-reload on code changes
- **PostgreSQL 15** - Database with auto-migrations
- **Redis 7** - Caching and sessions
- **Adminer** - Database UI at `http://localhost:8080`

### Environment

Development uses simplified credentials:
- **DB Username:** `postgres`
- **DB Password:** `postgres`
- **Redis:** No password (dev only)
- **Database:** `postgresql+asyncpg://postgres:postgres@db:5432/sports_platform`

### Accessing Services

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:8000 | REST API & WebSocket |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Adminer | http://localhost:8080 | Database management |

---

## Production Setup

### Pre-Deployment

1. **Prepare Environment**

```bash
# Create production env file
cp .env.example .env.production

# Generate secure secret key
openssl rand -hex 32  # Use output for SECRET_KEY

# Set required variables in .env.production
export DB_PASSWORD="your-secure-password"
export REDIS_PASSWORD="your-secure-password"
```

2. **SSL Certificates**

```bash
# For Let's Encrypt with Certbot
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Copy certificates to nginx
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ssl/key.pem
```

3. **Update Nginx Config**

Edit `nginx.conf`:
- Change `yourdomain.com` to your actual domain
- Update SSL certificate paths
- Verify upstream server names match your deployment

### Deploy

```bash
# Build and start production services
docker-compose -f docker-compose.yml up -d

# Run database migrations
docker-compose exec api alembic upgrade head

# Verify health
curl http://localhost:8000/health

# View logs
docker-compose logs -f api
```

### Scaling

To run multiple API instances:

```yaml
# docker-compose.yml - services.api
deploy:
  replicas: 3  # Or use docker-compose up --scale api=3
```

Update nginx.conf upstream:
```nginx
upstream api_backend {
    least_conn;
    server api:8000;
    server api:8001;
    server api:8002;
}
```

---

## Dockerfile Improvements

### Multi-Stage Build
- **Builder stage** - Compiles Python dependencies, installs build tools
- **Runtime stage** - Only runtime dependencies, smaller final image

### Security
- Non-root user (`appuser`) - prevents container escape attacks
- No unnecessary packages in final image
- No secrets in image layers

### Performance
- Auto-calculated worker count: `2 * CPU_cores + 1`
- Health checks for orchestration (Kubernetes, Docker Swarm)
- Proper logging to stdout/stderr for container logs

### Health Check
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```

---

## Docker Compose Improvements

### Version 3.9 Features
- Named volumes with proper drivers
- Custom networks for service isolation
- Resource limits per service (CPU, Memory)
- Health checks with proper wait conditions
- JSON logging with rotation

### Environment Variables

**API Service:**
- `DATABASE_URL` - Postgres connection in docker network
- `REDIS_URL` - Redis connection for caching
- `DEBUG` - Set to `False` in production
- `ENVIRONMENT` - Set to `production`

**Database:**
- `POSTGRES_DB` - Database name
- `POSTGRES_USER` - Database user
- `POSTGRES_PASSWORD` - Secure password (use env var)
- Performance tuning: `max_connections=200`, `shared_buffers=256MB`

**Redis:**
- `--requirepass` - Password protection
- `--appendonly yes` - Data persistence

### Resource Limits

```yaml
deploy:
  resources:
    limits:
      cpus: '1'           # Maximum 1 CPU
      memory: 512M        # Maximum 512MB RAM
    reservations:
      cpus: '0.5'         # Guaranteed 0.5 CPU
      memory: 256M        # Guaranteed 256MB RAM
```

Prevent one service from consuming all resources.

---

## Nginx Configuration

### Security Features

1. **SSL/TLS**
   - TLS 1.2+ only (no old SSL)
   - Strong cipher suites
   - HTTP/2 support
   - HSTS headers (force HTTPS)

2. **Security Headers**
   - `X-Content-Type-Options: nosniff` - Prevent MIME sniffing
   - `X-Frame-Options: DENY` - Prevent clickjacking
   - `X-XSS-Protection` - Browser XSS filter
   - `Strict-Transport-Security` - Force HTTPS for 1 year

3. **Rate Limiting**
   - General API: 10 requests/second
   - Auth endpoints: 5 requests/second
   - Protects against brute force attacks

### Performance Features

1. **Gzip Compression**
   - Reduces response size by 60-80%
   - Applied to JSON, HTML, CSS, JS

2. **HTTP/2**
   - Multiplexing for faster parallel requests
   - Server push capability

3. **Caching**
   - Static assets: 30 days
   - API docs: 1 hour
   - Proper cache headers

4. **Load Balancing**
   ```nginx
   upstream api_backend {
       least_conn;  # Use least connections
       server api:8000;
       server api:8001;  # For scaling
   }
   ```

### WebSocket Configuration

```nginx
location /ws/ {
    proxy_read_timeout 300s;    # 5 minutes
    proxy_buffering off;         # Disable buffering
    # Upgrade headers for protocol switch
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

---

## .dockerignore Optimization

Reduces build context size:
- Excludes `.git`, test files, docs
- Excludes IDE configs, venv, __pycache__
- Faster builds, smaller Docker contexts

---

## Monitoring & Logging

### Container Logs

```bash
# Real-time logs
docker-compose logs -f api

# Last 100 lines
docker-compose logs api --tail 100

# Specific service
docker-compose logs db
```

### Health Checks

```bash
# Check container status
docker-compose ps

# Run health check manually
docker-compose exec api curl http://localhost:8000/health
```

### Logs Rotation

All services use JSON logging with:
- Max file size: 10MB
- Max files: 3
- Auto-rotation to prevent disk space issues

---

## Database Migrations

### Initialize Database

```bash
# Run migrations in production
docker-compose exec api alembic upgrade head

# Check migration status
docker-compose exec api alembic current

# Rollback last migration
docker-compose exec api alembic downgrade -1
```

### Create New Migration

```bash
docker-compose exec api alembic revision --autogenerate -m "description"
docker-compose exec api alembic upgrade head
```

---

## Troubleshooting

### Issue: "Connection refused" to database

```bash
# Check if database is healthy
docker-compose ps db

# View database logs
docker-compose logs db

# Wait longer for database startup
docker-compose down && docker-compose up -d
```

### Issue: "Container exited with code 1"

```bash
# Check logs
docker-compose logs api

# Verify environment variables
docker-compose config | grep -A 20 "services:"

# Test local startup
docker-compose run api python app/main.py
```

### Issue: Permission denied on volumes

```bash
# Fix permissions
docker-compose down
sudo chown -R $USER:$USER postgres_data redis_data
docker-compose up -d
```

### Issue: Port already in use

```bash
# Check what's using port 8000
lsof -i :8000

# Kill process or use different port
docker-compose -p new_port up -d
```

---

## Best Practices

✅ **Do:**
- Use environment variables for all secrets
- Run containers with non-root users
- Set resource limits
- Use health checks
- Log to stdout/stderr
- Version your dependencies
- Use .dockerignore

❌ **Don't:**
- Store secrets in Dockerfile or environment files
- Run as root user
- Commit .env files to version control
- Ignore Docker security warnings
- Use `latest` tags in production
- Run without resource limits

---

## Additional Resources

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Docker Security](https://docs.docker.com/engine/security/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [PostgreSQL Docker](https://hub.docker.com/_/postgres)
- [Redis Docker](https://hub.docker.com/_/redis)

---

## Support

For issues or questions:
1. Check container logs: `docker-compose logs <service>`
2. Verify environment variables: `docker-compose config`
3. Review Docker Compose file: `docker-compose ps`
