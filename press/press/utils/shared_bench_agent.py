"""
Shared Bench Agent

This module provides a SharedBenchAgent class that mirrors the Agent interface
but executes operations via Kubernetes exec instead of HTTP calls to server agents.

This enables the shared bench multi-tenancy model where all sites run on the same
Kubernetes deployment.
"""

import json
import frappe
from frappe.utils import now_datetime, random_string
from press.press.utils.shared_bench import (
    is_shared_bench_mode,
    get_shared_bench_config,
    get_database_name,
)


class SharedBenchJob:
    """
    Represents an async job on the shared bench.
    
    Mimics AgentJob behavior for compatibility with existing Press code.
    """
    
    def __init__(self, job_type, site_name, status="Pending", data=None):
        self.name = f"SBJ-{random_string(10)}"
        self.job_type = job_type
        self.site = site_name
        self.status = status
        self.data = data or {}
        self.creation = now_datetime()
        self.output = ""
        self.error = ""
        
    def to_dict(self):
        return {
            "name": self.name,
            "job_type": self.job_type,
            "site": self.site,
            "status": self.status,
            "data": self.data,
            "creation": str(self.creation),
            "output": self.output,
            "error": self.error,
        }
    
    def set_success(self, output=""):
        self.status = "Success"
        self.output = output
        
    def set_failure(self, error=""):
        self.status = "Failure"
        self.error = error


class SharedBenchAgent:
    """
    Agent replacement for shared bench mode.
    
    Instead of making HTTP calls to server agents, this executes bench commands
    directly via Kubernetes exec into the backend pod.
    
    Maintains API compatibility with the original Agent class.
    """
    
    def __init__(self, server=None, server_type="Server"):
        """
        Initialize SharedBenchAgent
        
        Args:
            server: Server document (ignored in shared bench mode)
            server_type: Type of server (ignored in shared bench mode)
        """
        self.server = server
        self.server_type = server_type
        self.config = get_shared_bench_config()
        
        # Lazy load the bench manager
        self._bench_manager = None
    
    @property
    def bench_manager(self):
        if self._bench_manager is None:
            from press.press.utils.kubernetes import get_shared_bench_manager
            self._bench_manager = get_shared_bench_manager()
        return self._bench_manager
    
    def new_site(self, site, create_user=None):
        """
        Create a new site on the shared bench
        
        Args:
            site: Site document
            create_user: Optional dict with user creation info
        
        Returns:
            SharedBenchJob: Job representing the operation
        """
        job = SharedBenchJob("New Site", site.name)
        
        try:
            # Get apps to install
            apps = [app.app for app in site.apps]
            
            # Get admin password
            admin_password = site.get_password("admin_password") or 'admin'
            
            # Get database root password from config
            db_root_password = self.config['db_root_password']
            
            # Execute site creation
            result = self.bench_manager.create_site(
                site_name=site.name,
                admin_password=admin_password,
                db_root_password=db_root_password,
                install_apps=apps
            )
            
            # Apply site config if provided
            config = json.loads(site.config) if site.config else {}
            if config:
                self.bench_manager.set_config(site.name, config)
            
            # Create user if requested
            if create_user:
                self._create_site_user(site.name, create_user)
            
            job.set_success(f"Site {site.name} created successfully")
            
            # Update site status
            frappe.db.set_value("Site", site.name, "status", "Active")
            frappe.db.commit()
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to create site {site.name}: {e}")
        
        return job
    
    def reinstall_site(self, site, create_user=None):
        """
        Reinstall a site (drop and recreate)
        
        Args:
            site: Site document
            create_user: Optional user creation info
        
        Returns:
            SharedBenchJob
        """
        job = SharedBenchJob("Reinstall Site", site.name)
        
        try:
            db_root_password = self.config['db_root_password']
            
            # Drop the site first
            self.bench_manager.drop_site(
                site_name=site.name,
                db_root_password=db_root_password
            )
            
            # Recreate the site
            apps = [app.app for app in site.apps]
            admin_password = site.get_password("admin_password") or 'admin'
            
            self.bench_manager.create_site(
                site_name=site.name,
                admin_password=admin_password,
                db_root_password=db_root_password,
                install_apps=apps
            )
            
            if create_user:
                self._create_site_user(site.name, create_user)
            
            job.set_success(f"Site {site.name} reinstalled successfully")
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to reinstall site {site.name}: {e}")
        
        return job
    
    def migrate_site(self, site, skip_failing_patches=False):
        """
        Run migrations on a site
        
        Args:
            site: Site document
            skip_failing_patches: Skip patches that fail
        
        Returns:
            SharedBenchJob
        """
        job = SharedBenchJob("Migrate Site", site.name)
        
        try:
            result = self.bench_manager.migrate_site(
                site_name=site.name,
                skip_failing_patches=skip_failing_patches
            )
            job.set_success(f"Site {site.name} migrated successfully")
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to migrate site {site.name}: {e}")
        
        return job
    
    def backup_site(self, site, with_files=True, offsite=False):
        """
        Create a backup of the site
        
        Args:
            site: Site document or site name string
            with_files: Include files in backup
            offsite: Upload to offsite storage
        
        Returns:
            SharedBenchJob
        """
        site_name = site.name if hasattr(site, 'name') else site
        job = SharedBenchJob("Backup Site", site_name)
        
        try:
            result = self.bench_manager.backup_site(
                site_name=site_name,
                with_files=with_files
            )
            job.set_success(f"Backup created for {site_name}")
            job.data['backup_path'] = result.get('backup_path', '')
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to backup site {site_name}: {e}")
        
        return job
    
    def restore_site(self, site, backup, skip_failing_patches=False):
        """
        Restore a site from backup
        
        Args:
            site: Site document
            backup: Backup document or path
            skip_failing_patches: Skip patches that fail during restore
        
        Returns:
            SharedBenchJob
        """
        job = SharedBenchJob("Restore Site", site.name)
        
        try:
            backup_path = backup.database_file if hasattr(backup, 'database_file') else backup
            
            result = self.bench_manager.restore_site(
                site_name=site.name,
                backup_path=backup_path,
                db_root_password=self.config['db_root_password']
            )
            job.set_success(f"Site {site.name} restored successfully")
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to restore site {site.name}: {e}")
        
        return job
    
    def archive_site(self, site, site_name=None, reason=None):
        """
        Archive (delete) a site
        
        Args:
            site: Site document
            site_name: Name of site (optional)
            reason: Reason for archiving
        
        Returns:
            SharedBenchJob
        """
        site_name = site_name or site.name
        job = SharedBenchJob("Archive Site", site_name)
        
        try:
            # Take final backup before archiving
            self.bench_manager.backup_site(site_name, with_files=True)
            
            # Drop the site
            self.bench_manager.drop_site(
                site_name=site_name,
                db_root_password=self.config['db_root_password']
            )
            
            job.set_success(f"Site {site_name} archived successfully")
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to archive site {site_name}: {e}")
        
        return job
    
    def install_app_site(self, site, app):
        """
        Install an app on a site
        
        Args:
            site: Site document
            app: App name to install
        
        Returns:
            SharedBenchJob
        """
        job = SharedBenchJob("Install App", site.name)
        
        try:
            result = self.bench_manager.install_app(site.name, app)
            job.set_success(f"App {app} installed on {site.name}")
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to install {app} on {site.name}: {e}")
        
        return job
    
    def uninstall_app_site(self, site, app):
        """
        Uninstall an app from a site
        
        Args:
            site: Site document
            app: App name to uninstall
        
        Returns:
            SharedBenchJob
        """
        job = SharedBenchJob("Uninstall App", site.name)
        
        try:
            result = self.bench_manager.exec_bench_command(
                f"--site {site.name} uninstall-app {app} --yes"
            )
            job.set_success(f"App {app} uninstalled from {site.name}")
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to uninstall {app} from {site.name}: {e}")
        
        return job
    
    def update_site_config(self, site):
        """
        Update site configuration
        
        Args:
            site: Site document with updated config
        
        Returns:
            SharedBenchJob
        """
        job = SharedBenchJob("Update Site Config", site.name)
        
        try:
            config = json.loads(site.config) if site.config else {}
            if config:
                self.bench_manager.set_config(site.name, config)
            job.set_success(f"Config updated for {site.name}")
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to update config for {site.name}: {e}")
        
        return job
    
    def clear_site_cache(self, site):
        """
        Clear cache for a site
        
        Args:
            site: Site document
        
        Returns:
            SharedBenchJob
        """
        job = SharedBenchJob("Clear Cache", site.name)
        
        try:
            result = self.bench_manager.exec_bench_command(
                f"--site {site.name} clear-cache"
            )
            job.set_success(f"Cache cleared for {site.name}")
            
        except Exception as e:
            job.set_failure(str(e))
            frappe.log_error(f"Failed to clear cache for {site.name}: {e}")
        
        return job
    
    def enable_scheduler(self, site):
        """Enable scheduler for a site"""
        job = SharedBenchJob("Enable Scheduler", site.name)
        
        try:
            result = self.bench_manager.exec_bench_command(
                f"--site {site.name} enable-scheduler"
            )
            job.set_success(f"Scheduler enabled for {site.name}")
        except Exception as e:
            job.set_failure(str(e))
        
        return job
    
    def disable_scheduler(self, site):
        """Disable scheduler for a site"""
        job = SharedBenchJob("Disable Scheduler", site.name)
        
        try:
            result = self.bench_manager.exec_bench_command(
                f"--site {site.name} disable-scheduler"
            )
            job.set_success(f"Scheduler disabled for {site.name}")
        except Exception as e:
            job.set_failure(str(e))
        
        return job
    
    def set_admin_password(self, site, password):
        """Set admin password for a site"""
        job = SharedBenchJob("Set Admin Password", site.name)
        
        try:
            result = self.bench_manager.exec_bench_command(
                f"--site {site.name} set-admin-password {password}"
            )
            job.set_success(f"Admin password updated for {site.name}")
        except Exception as e:
            job.set_failure(str(e))
        
        return job
    
    def _create_site_user(self, site_name, user_info):
        """
        Create a user on the site
        
        Args:
            site_name: Name of the site
            user_info: Dict with email, first_name, last_name
        """
        email = user_info.get('email')
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')
        
        if not email:
            return
        
        # Use bench execute to create user
        command = f"""--site {site_name} execute frappe.core.doctype.user.user.create_user --args "['{email}']" --kwargs "{{\\"first_name\\": \\"{first_name}\\", \\"last_name\\": \\"{last_name}\\", \\"send_welcome_email\\": false}}" """
        
        try:
            self.bench_manager.exec_bench_command(command)
        except Exception as e:
            frappe.log_error(f"Failed to create user {email} on {site_name}: {e}")


def get_agent(server=None, server_type="Server"):
    """
    Factory function to get the appropriate agent based on mode.
    
    In shared bench mode, returns SharedBenchAgent.
    Otherwise, returns the standard Agent.
    
    Args:
        server: Server document
        server_type: Type of server
    
    Returns:
        Agent or SharedBenchAgent instance
    """
    if is_shared_bench_mode():
        return SharedBenchAgent(server, server_type)
    else:
        # Import here to avoid circular imports
        from press.agent import Agent
        return Agent(server, server_type)
