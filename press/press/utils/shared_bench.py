"""
Shared Bench Mode Configuration and Utilities

This module provides configuration and utilities for running Press in shared bench mode,
where all tenant sites run on a single shared ERPNext installation instead of separate servers.
"""

import frappe


def is_shared_bench_mode():
    """Check if Press is running in shared bench mode"""
    return frappe.conf.get('shared_bench_enabled', False)


def get_shared_bench_config():
    """Get shared bench configuration from site_config.json"""
    return {
        'enabled': frappe.conf.get('shared_bench_enabled', False),
        'namespace': frappe.conf.get('shared_bench_namespace', 'erpnext'),
        'pod_label': frappe.conf.get('shared_bench_pod_label', 'app=erpnext,component=backend'),
        'db_host': frappe.conf.get('shared_bench_db_host', 'mariadb'),
        'db_root_password': frappe.conf.get('db_root_password', ''),
        'redis_cache': frappe.conf.get('shared_bench_redis_cache', 'redis://redis-cache:6379'),
        'redis_queue': frappe.conf.get('shared_bench_redis_queue', 'redis://redis-queue:6379'),
        'default_apps': frappe.conf.get('shared_bench_default_apps', ['frappe', 'erpnext']),
    }


def get_database_name(site_domain):
    """
    Convert site domain to valid MySQL database name
    
    Args:
        site_domain: Domain name (e.g., tenant1.erp.web.com.do)
    
    Returns:
        str: Valid database name (e.g., tenant1_erp_web_com_do)
    """
    # MySQL database names: max 64 chars, alphanumeric + underscore
    db_name = site_domain.replace('.', '_').replace('-', '_')
    # Ensure it doesn't start with a number
    if db_name[0].isdigit():
        db_name = f"site_{db_name}"
    # Truncate if too long
    return db_name[:64]


def get_database_user(site_domain):
    """
    Generate database user for a site
    
    Args:
        site_domain: Domain name
    
    Returns:
        str: Database username (max 32 chars for MySQL)
    """
    return get_database_name(site_domain)[:32]


def validate_shared_bench_config():
    """Validate shared bench configuration"""
    if not is_shared_bench_mode():
        return True
    
    config = get_shared_bench_config()
    
    errors = []
    
    if not config['namespace']:
        errors.append("shared_bench_namespace is required")
    
    if not config['db_root_password']:
        errors.append("db_root_password is required for shared bench mode")
    
    if errors:
        frappe.throw("Shared bench configuration errors: " + ", ".join(errors))
    
    return True


class SharedBenchSiteManager:
    """
    High-level manager for site operations in shared bench mode.
    
    This replaces the Agent-based communication with direct Kubernetes operations.
    """
    
    def __init__(self):
        self.config = get_shared_bench_config()
        
        if not self.config['enabled']:
            frappe.throw("Shared bench mode is not enabled")
        
        # Import here to avoid loading kubernetes if not needed
        from press.press.utils.kubernetes import get_shared_bench_manager
        self.bench_manager = get_shared_bench_manager()
    
    def create_site(self, site_doc):
        """
        Create a new site on the shared bench
        
        Args:
            site_doc: Site document instance
        """
        # Get apps to install
        apps = [app.app for app in site_doc.apps]
        
        # Get admin password
        admin_password = site_doc.get_password("admin_password") or 'admin'
        
        # Create the site
        self.bench_manager.create_site(
            site_name=site_doc.name,
            admin_password=admin_password,
            db_root_password=self.config['db_root_password'],
            install_apps=apps
        )
        
        # Update site status
        frappe.db.set_value("Site", site_doc.name, "status", "Active")
        
        return True
    
    def drop_site(self, site_doc):
        """
        Drop a site from the shared bench
        
        Args:
            site_doc: Site document instance
        """
        self.bench_manager.drop_site(
            site_name=site_doc.name,
            db_root_password=self.config['db_root_password']
        )
        
        return True
    
    def backup_site(self, site_doc, with_files=True):
        """
        Create backup of a site
        
        Args:
            site_doc: Site document instance
            with_files: Include files in backup
        """
        return self.bench_manager.backup_site(
            site_name=site_doc.name,
            with_files=with_files
        )
    
    def migrate_site(self, site_doc):
        """
        Run migrations on a site
        
        Args:
            site_doc: Site document instance
        """
        return self.bench_manager.migrate_site(site_doc.name)
    
    def install_app(self, site_doc, app_name):
        """
        Install an app on a site
        
        Args:
            site_doc: Site document instance
            app_name: Name of app to install
        """
        return self.bench_manager.install_app(site_doc.name, app_name)
    
    def get_site_info(self, site_doc):
        """
        Get information about a site
        
        Args:
            site_doc: Site document instance
        """
        return self.bench_manager.get_site_info(site_doc.name)


# Singleton instance
_site_manager = None

def get_shared_bench_site_manager():
    """Get or create SharedBenchSiteManager instance"""
    global _site_manager
    if _site_manager is None:
        _site_manager = SharedBenchSiteManager()
    return _site_manager
