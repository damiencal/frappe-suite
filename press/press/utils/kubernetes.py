"""
Kubernetes Operations for Shared Multi-Tenant Bench

This module provides Kubernetes operations for managing sites on a shared ERPNext bench.
Instead of provisioning separate servers, all sites run on the same set of pods.
"""

import frappe
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
import json


class SharedBenchManager:
    """Manages operations on shared ERPNext bench running in Kubernetes"""
    
    def __init__(self):
        """Initialize Kubernetes client"""
        try:
            # Try in-cluster config first (when running in K8s)
            config.load_incluster_config()
        except:
            # Fall back to kubeconfig (for development)
            config.load_kube_config()
        
        self.core_v1 = client.CoreV1Api()
        self.namespace = frappe.conf.get('shared_bench_namespace', 'erpnext')
        self.pod_label = frappe.conf.get('shared_bench_pod_label', 'app=erpnext,component=backend')
    
    def get_backend_pod(self):
        """Get a running backend pod from the shared bench"""
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=self.pod_label
            )
            
            for pod in pods.items:
                if pod.status.phase == 'Running':
                    return pod.metadata.name
            
            raise Exception("No running backend pods found")
        except ApiException as e:
            frappe.throw(f"Failed to get backend pod: {e}")
    
    def exec_bench_command(self, command, site=None):
        """
        Execute a bench command in the shared bench pod
        
        Args:
            command: Bench command to execute (e.g., "bench new-site example.com")
            site: Optional site context for site-specific commands
        
        Returns:
            tuple: (stdout, stderr, exit_code)
        """
        pod_name = self.get_backend_pod()
        
        # Build full command
        exec_command = [
            "/bin/bash",
            "-c",
            f"cd /home/frappe/frappe-bench && {command}"
        ]
        
        try:
            resp = stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                self.namespace,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _preload_content=False
            )
            
            stdout, stderr = "", ""
            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    stdout += resp.read_stdout()
                if resp.peek_stderr():
                    stderr += resp.read_stderr()
            
            resp.close()
            
            # Get exit code
            exit_code = resp.returncode if hasattr(resp, 'returncode') else 0
            
            return stdout, stderr, exit_code
            
        except ApiException as e:
            frappe.throw(f"Failed to execute command: {e}")
    
    def create_site(self, site_name, admin_password='admin', db_root_password=None, install_apps=None):
        """
        Create a new site on the shared bench
        
        Args:
            site_name: Domain name of the site (e.g., tenant1.erp.web.com.do)
            admin_password: Administrator password
            db_root_password: MariaDB root password
            install_apps: List of apps to install (default: ['erpnext'])
        """
        if not db_root_password:
            db_root_password = frappe.conf.get('db_root_password')
        
        if not install_apps:
            install_apps = ['erpnext']
        
        # Build bench new-site command
        command = f"""bench new-site {site_name} \\
            --db-root-password '{db_root_password}' \\
            --admin-password '{admin_password}' \\
            --mariadb-user-host-login-scope='%'"""
        
        frappe.logger().info(f"Creating site: {site_name}")
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        if exit_code != 0:
            frappe.throw(f"Site creation failed: {stderr}")
        
        # Install apps
        for app in install_apps:
            self.install_app(site_name, app)
        
        frappe.logger().info(f"Site created successfully: {site_name}")
        return True
    
    def install_app(self, site_name, app_name):
        """Install an app on a site"""
        command = f"bench --site {site_name} install-app {app_name}"
        
        frappe.logger().info(f"Installing {app_name} on {site_name}")
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        if exit_code != 0:
            frappe.throw(f"App installation failed: {stderr}")
        
        return True
    
    def migrate_site(self, site_name):
        """Run migrate on a site"""
        command = f"bench --site {site_name} migrate"
        
        frappe.logger().info(f"Running migrate on {site_name}")
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        return exit_code == 0
    
    def backup_site(self, site_name, with_files=True):
        """Create a backup of a site"""
        files_flag = "--with-files" if with_files else ""
        command = f"bench --site {site_name} backup {files_flag}"
        
        frappe.logger().info(f"Backing up {site_name}")
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        if exit_code != 0:
            frappe.throw(f"Backup failed: {stderr}")
        
        return True
    
    def restore_site(self, site_name, sql_file, with_files=None):
        """Restore a site from backup"""
        files_flag = f"--with-public-files {with_files}" if with_files else ""
        command = f"bench --site {site_name} restore {sql_file} {files_flag}"
        
        frappe.logger().info(f"Restoring {site_name}")
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        if exit_code != 0:
            frappe.throw(f"Restore failed: {stderr}")
        
        return True
    
    def drop_site(self, site_name, db_root_password=None):
        """Drop a site"""
        if not db_root_password:
            db_root_password = frappe.conf.get('db_root_password')
        
        command = f"bench drop-site {site_name} --db-root-password '{db_root_password}' --force"
        
        frappe.logger().info(f"Dropping site: {site_name}")
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        if exit_code != 0:
            frappe.log_error(f"Site drop failed: {stderr}")
            return False
        
        return True
    
    def get_site_info(self, site_name):
        """Get information about a site"""
        command = f"bench --site {site_name} version --format json"
        
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        if exit_code != 0:
            return None
        
        try:
            return json.loads(stdout)
        except:
            return None
    
    def list_sites(self):
        """List all sites on the bench"""
        command = "bench list-sites --format json"
        
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        if exit_code != 0:
            return []
        
        try:
            return json.loads(stdout)
        except:
            return []
    
    def set_config(self, site_name, key, value):
        """Set a site config value"""
        command = f"bench --site {site_name} set-config {key} '{value}'"
        
        stdout, stderr, exit_code = self.exec_bench_command(command)
        return exit_code == 0
    
    def reload_bench(self):
        """Reload the bench processes"""
        command = "bench restart"
        
        frappe.logger().info("Reloading bench")
        stdout, stderr, exit_code = self.exec_bench_command(command)
        
        return exit_code == 0


# Singleton instance
_manager = None

def get_shared_bench_manager():
    """Get or create SharedBenchManager instance"""
    global _manager
    if _manager is None:
        _manager = SharedBenchManager()
    return _manager
