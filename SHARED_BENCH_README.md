# Frappe Press - Shared Bench Multi-tenancy

This fork of Frappe Press enables shared bench multi-tenancy mode where all tenant sites run on a single shared ERPNext Kubernetes deployment.

## Architecture

### Traditional Press (Server-per-tenant)
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Tenant A   │     │  Tenant B   │     │  Tenant C   │
│  Server     │     │  Server     │     │  Server     │
│  ┌───────┐  │     │  ┌───────┐  │     │  ┌───────┐  │
│  │ERPNext│  │     │  │ERPNext│  │     │  │ERPNext│  │
│  └───────┘  │     │  └───────┘  │     │  └───────┘  │
│  ┌───────┐  │     │  ┌───────┐  │     │  ┌───────┐  │
│  │MariaDB│  │     │  │MariaDB│  │     │  │MariaDB│  │
│  └───────┘  │     │  └───────┘  │     │  └───────┘  │
└─────────────┘     └─────────────┘     └─────────────┘
```

### Shared Bench Mode (This fork)
```
┌─────────────────────────────────────────────────────┐
│                 Shared ERPNext Pod                   │
│  ┌─────────────────────────────────────────────┐    │
│  │           ERPNext Application                │    │
│  │  ┌──────────┬──────────┬──────────┐         │    │
│  │  │ Site A   │ Site B   │ Site C   │ ...     │    │
│  │  └──────────┴──────────┴──────────┘         │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│                   Shared MariaDB                     │
│  ┌──────────┬──────────┬──────────┬─────────────┐  │
│  │ DB: A    │ DB: B    │ DB: C    │ ...         │  │
│  └──────────┴──────────┴──────────┴─────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Benefits

| Metric | Traditional | Shared Bench | Savings |
|--------|-------------|--------------|---------|
| Memory per tenant | 2GB | 0.5GB | 75% |
| Containers per tenant | 6 | 0 | 100% |
| Provisioning time | 5-10 min | <30 sec | 95% |
| App updates | Per tenant | Once | 90% |

## Quick Start

### 1. Configure Site Config

Add to your Press site's `site_config.json`:

```json
{
    "shared_bench_enabled": true,
    "shared_bench_namespace": "erpnext",
    "shared_bench_pod_label": "app=erpnext,component=backend",
    "db_root_password": "your_mariadb_root_password"
}
```

### 2. Deploy ERPNext on Kubernetes

Deploy a standard ERPNext installation using frappe_docker:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: erpnext-backend
  namespace: erpnext
spec:
  replicas: 1
  selector:
    matchLabels:
      app: erpnext
      component: backend
  template:
    metadata:
      labels:
        app: erpnext
        component: backend
    spec:
      containers:
      - name: backend
        image: frappe/erpnext:v15
```

### 3. Deploy Modified Press

```bash
# Build the image
./build.sh

# Or use pre-built
docker pull ghcr.io/damiencal/frappe-press:v15-shared
```

## How It Works

### Site Creation Flow

1. User creates site via Press dashboard
2. `SharedBenchSiteController.after_insert()` is triggered
3. `SharedBenchAgent.new_site()` is called instead of regular Agent
4. `SharedBenchManager` executes `bench new-site` via Kubernetes exec
5. Site is created on shared ERPNext pod with its own database

### Key Components

```
press/press/utils/
├── __init__.py              # Module exports + initialize_shared_bench()
├── kubernetes.py            # SharedBenchManager - K8s exec operations
├── shared_bench.py          # Configuration and site manager
├── shared_bench_agent.py    # SharedBenchAgent (Agent API compatible)
├── site_patches.py          # Site doctype hooks for shared mode
└── virtual_server.py        # Virtual server/bench for Press compatibility
```

### SharedBenchAgent Methods

All Agent methods are implemented to work via Kubernetes exec:

- `new_site()` - Create new site
- `reinstall_site()` - Drop and recreate site
- `migrate_site()` - Run migrations
- `backup_site()` - Create backup
- `restore_site()` - Restore from backup
- `archive_site()` - Delete site
- `install_app_site()` - Install app
- `uninstall_app_site()` - Uninstall app
- `update_site_config()` - Update site config
- `clear_site_cache()` - Clear cache
- `enable_scheduler()` / `disable_scheduler()`
- `set_admin_password()`

## Configuration Reference

| Setting | Description | Default |
|---------|-------------|---------|
| `shared_bench_enabled` | Enable shared bench mode | `false` |
| `shared_bench_namespace` | Kubernetes namespace | `erpnext` |
| `shared_bench_pod_label` | Label to find backend pod | `app=erpnext,component=backend` |
| `db_root_password` | MariaDB root password | Required |
| `shared_bench_db_host` | MariaDB host | `mariadb` |
| `shared_bench_redis_cache` | Redis cache URL | `redis://redis-cache:6379` |
| `shared_bench_redis_queue` | Redis queue URL | `redis://redis-queue:6379` |
| `shared_bench_default_apps` | Default apps for new sites | `["frappe", "erpnext"]` |

## Limitations

1. **No per-tenant app versions** - All tenants share the same ERPNext version
2. **No custom apps per tenant** - Custom apps must be installed globally
3. **Shared resource limits** - All tenants share the same pod resources
4. **No tenant isolation** - Sites share the same application process

## Branch

All changes are on the `shared-multitenancy` branch:

```bash
git checkout shared-multitenancy
```

## License

GNU Affero General Public License v3.0 (same as Frappe Press)
