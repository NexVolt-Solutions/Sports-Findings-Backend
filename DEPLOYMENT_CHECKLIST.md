# Production Deployment Checklist

## Pre-Deployment (1-2 Days Before)

### Security & Secrets
- [ ] Generate secure `SECRET_KEY`: `openssl rand -hex 32`
- [ ] Generate secure `DB_PASSWORD` (20+ chars, mixed case + numbers + symbols)
- [ ] Generate secure `REDIS_PASSWORD`
- [ ] Store all secrets in secure vault (AWS Secrets Manager, Vault, LastPass, etc.)
- [ ] Do NOT commit `.env.production` to version control
- [ ] Review `.env.example` for all required variables
- [ ] Ensure all API keys are valid (Google OAuth, Google Maps, Cloudinary, Firebase)

### Infrastructure
- [ ] Provision server/VM with minimum specs:
  - 2+ CPU cores
  - 4GB+ RAM
  - 20GB+ disk space
  - Ubuntu 20.04 LTS or similar
- [ ] Install Docker and Docker Compose
- [ ] Configure firewall (allow ports 80, 443, 22 only)
- [ ] Setup SSL certificates with Let's Encrypt
- [ ] Create `/var/log/sports-platform/` directory with proper permissions
- [ ] Setup log rotation with logrotate

### Domain & DNS
- [ ] Domain registered and verified
- [ ] DNS A/AAAA records point to server IP
- [ ] SSL certificate requested and validated for domain
- [ ] Update Nginx config with correct domain name

### Database
- [ ] Create backup of staging database (if migrating from staging)
- [ ] Verify Alembic migrations are up-to-date
- [ ] Test migration process: `alembic upgrade head`
- [ ] Create database user with limited permissions (not root)
- [ ] Setup automated backups (daily snapshots)
- [ ] Document backup recovery procedure
- [ ] Test backup restoration on separate instance

### Email Configuration
- [ ] Gmail SMTP credentials configured
- [ ] Test email sending with `send_verification_email`
- [ ] Configure SPF/DKIM/DMARC records for email domain
- [ ] Setup email bounce handling

### External Services
- [ ] Google OAuth app created and credentials configured
- [ ] Google Maps API enabled and key created
- [ ] Cloudinary account setup with API credentials
- [ ] Firebase project setup with service account
- [ ] All API keys added to `.env.production`

### Code Quality
- [ ] All tests passing: `pytest tests/`
- [ ] Code reviewed and approved
- [ ] No commented-out code or debug statements
- [ ] Logging configured for production (no debug logs by default)
- [ ] Error handling verified (no stack traces in responses)

---

## Deployment Day

### Pre-Deployment Verification
- [ ] Backup current production database (if migrating)
- [ ] Document current production version/commit
- [ ] Plan rollback strategy
- [ ] Schedule maintenance window (if needed)
- [ ] Notify users of deployment if downtime expected

### Deployment Steps

#### 1. Prepare Environment
```bash
# SSH into production server
ssh user@production-server

# Navigate to app directory
cd /opt/sports-platform

# Create .env.production with all secrets
nano .env.production
```

#### 2. Pull Code & Update
```bash
# Pull latest code
git pull origin main

# Verify Dockerfile and compose files
cat Dockerfile
cat docker-compose.yml
```

#### 3. Build Docker Image
```bash
# Build with production tag
docker-compose build --no-cache api

# Verify image size (should be < 500MB)
docker images | grep sports-platform
```

#### 4. Database Migrations
```bash
# Run migrations before starting services
docker-compose exec -T db psql -U postgres -d sports_platform < migrations.sql

# Or with Alembic
docker-compose run --rm api alembic upgrade head
```

#### 5. Start Services
```bash
# Start all services
docker-compose up -d

# Wait for services to become healthy (30-60 seconds)
docker-compose ps

# Verify health checks pass
docker-compose exec api curl http://localhost:8000/health
```

#### 6. Post-Deployment Verification
```bash
# Verify all containers are running
docker-compose ps

# Check API is responding
curl -i http://localhost:8000/health

# Check database connectivity
docker-compose exec api python -c "from app.database import engine; print('DB OK')"

# Check Redis connectivity
docker-compose exec redis redis-cli ping

# View recent logs
docker-compose logs api --tail 50
docker-compose logs db --tail 20
```

---

## Post-Deployment

### Immediate (First 1 Hour)
- [ ] Monitor error logs for exceptions: `docker-compose logs -f api | grep ERROR`
- [ ] Check CPU/Memory usage: `docker stats`
- [ ] Verify database is healthy: `docker-compose logs db`
- [ ] Test critical endpoints:
  - `/health` - Health check
  - `/docs` - API documentation
  - `/api/v1/auth/login` - Authentication
  - WebSocket `/ws/notifications` - WebSocket
- [ ] Verify email notifications work
- [ ] Test file uploads (Cloudinary)
- [ ] Verify rate limiting works
- [ ] Check HTTPS is working and certificates are valid

### 24 Hours
- [ ] No errors in logs for past 24 hours
- [ ] Database backups completed successfully
- [ ] Performance metrics look normal (CPU < 70%, Memory < 80%)
- [ ] All background tasks completed successfully
- [ ] User reports confirmed everything works

### 1 Week
- [ ] Review logs for any unusual patterns
- [ ] Verify all scheduled tasks ran successfully
- [ ] Check disk space usage
- [ ] Database size is reasonable
- [ ] No security alerts

---

## Monitoring Setup

### Essential Monitoring

1. **Uptime Monitoring**
   ```bash
   # Setup with Pingdom, UptimeRobot, or similar
   - Monitor /health endpoint every 60 seconds
   - Alert on downtime > 5 minutes
   ```

2. **Log Aggregation**
   ```bash
   # Setup with ELK, Datadog, or similar
   - Centralize logs from all containers
   - Setup alerts for ERROR logs
   - Archive logs for 30 days minimum
   ```

3. **Performance Monitoring**
   ```bash
   # Setup with Prometheus, New Relic, or similar
   - Monitor CPU, Memory, Disk usage
   - Monitor database query times
   - Alert on resource exhaustion
   ```

4. **Error Tracking**
   ```bash
   # Setup with Sentry, Rollbar, or similar
   - Capture application exceptions
   - Group errors by type
   - Alert on critical errors
   ```

---

## Rollback Procedure

If deployment fails:

```bash
# 1. Stop current deployment
docker-compose down

# 2. Revert code to previous version
git checkout PREVIOUS_COMMIT

# 3. Rebuild images
docker-compose build --no-cache

# 4. Rollback database (if schema changed)
docker-compose exec api alembic downgrade -1

# 5. Restart services
docker-compose up -d

# 6. Verify health
docker-compose exec api curl http://localhost:8000/health
```

---

## Maintenance

### Daily
- [ ] Review error logs
- [ ] Monitor disk space (free space > 20%)

### Weekly
- [ ] Review performance metrics
- [ ] Check database size
- [ ] Verify backups completed

### Monthly
- [ ] Test backup restoration
- [ ] Review security logs
- [ ] Update Docker base images (patch security fixes)
- [ ] Review user reports/feedback

### Quarterly
- [ ] Load testing
- [ ] Security audit
- [ ] Database optimization (ANALYZE, VACUUM)
- [ ] Review and optimize costs

---

## Emergency Procedures

### Database Down
```bash
# Check database status
docker-compose logs db

# Restart database
docker-compose restart db

# Wait for recovery
sleep 30

# Verify health
docker-compose exec db pg_isready
```

### API High Memory Usage
```bash
# Check which process is consuming memory
docker stats

# Restart API service
docker-compose restart api

# Review logs for memory leaks
docker-compose logs api
```

### Disk Space Critical
```bash
# Check disk usage
df -h

# Clean old Docker layers
docker system prune -a

# Cleanup logs
docker-compose logs --tail 0 api > /dev/null

# Check if postgres is using too much space
du -sh postgres_data
```

### SSL Certificate Expired
```bash
# Renew certificate with Let's Encrypt
sudo certbot renew --force-renewal

# Copy to SSL directory
sudo cp /etc/letsencrypt/live/domain/fullchain.pem ssl/cert.pem
sudo cp /etc/letsencrypt/live/domain/privkey.pem ssl/key.pem

# Reload Nginx (without downtime)
docker-compose exec nginx nginx -s reload
```

---

## Success Criteria

Deployment is successful when:

✅ All containers running and healthy
✅ Health endpoint responds with 200 OK
✅ Database migrations completed
✅ No errors in application logs for 1 hour
✅ WebSocket connections working
✅ Email notifications working
✅ File uploads working
✅ Authentication working
✅ Rate limiting working
✅ Performance metrics normal
✅ SSL certificate valid

---

## Quick Reference

```bash
# View all running containers
docker-compose ps

# View real-time logs
docker-compose logs -f api

# Execute command in container
docker-compose exec api python app/main.py

# Rebuild images
docker-compose build --no-cache

# Run migrations
docker-compose exec api alembic upgrade head

# Database backup
docker-compose exec db pg_dump -U postgres sports_platform > backup.sql

# Database restore
docker-compose exec db psql -U postgres sports_platform < backup.sql

# Clean up unused images/volumes
docker system prune -a --volumes
```

---

## Support & Escalation

- **Critical Issues:** Page on-call engineer
- **High Priority:** Notify devops team within 15 minutes
- **Medium Priority:** Create ticket, review within 2 hours
- **Low Priority:** Log for next sprint review
