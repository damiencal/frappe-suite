"""
Site Patches for Shared Bench Mode

This module contains patches that are applied to the Site doctype
when running in shared bench mode.

These patches intercept agent calls and redirect them to SharedBenchAgent.
"""

import frappe
from press.press.utils.shared_bench import is_shared_bench_mode


def patch_site_class():
    """
    Patch the Site class to use SharedBenchAgent in shared bench mode.
    
    This should be called during app initialization (hooks.py)
    """
    if not is_shared_bench_mode():
        return
    
    from press.press.doctype.site.site import Site
    from press.press.utils.shared_bench_agent import SharedBenchAgent
    
    # Store original methods
    Site._original_app_server_agent = Site.app_server_agent
    Site._original_database_server_agent = Site.database_server_agent
    
    # Create new property that returns SharedBenchAgent
    @property
    def shared_app_server_agent(self):
        return SharedBenchAgent(self.server)
    
    @property
    def shared_database_server_agent(self):
        return SharedBenchAgent(self.database_server_name, server_type="Database Server")
    
    # Replace the properties
    Site.app_server_agent = shared_app_server_agent
    Site.database_server_agent = shared_database_server_agent
    
    frappe.logger().info("Site class patched for shared bench mode")


def get_site_agent(site_doc):
    """
    Get the appropriate agent for a site.
    
    In shared bench mode, returns SharedBenchAgent.
    Otherwise, returns the standard Agent.
    
    Args:
        site_doc: Site document instance
    
    Returns:
        Agent or SharedBenchAgent instance
    """
    if is_shared_bench_mode():
        from press.press.utils.shared_bench_agent import SharedBenchAgent
        return SharedBenchAgent(site_doc.server)
    else:
        from press.agent import Agent
        return Agent(site_doc.server)


class SharedBenchSiteController:
    """
    Controller mixin for Site doctype in shared bench mode.
    
    Provides override methods for site operations that need
    special handling in shared bench mode.
    """
    
    @staticmethod
    def before_insert(site):
        """
        Called before inserting a new site.
        
        In shared bench mode:
        - Skip server allocation (all sites share same server)
        - Validate site name format
        """
        if not is_shared_bench_mode():
            return
        
        # In shared bench mode, we use a virtual server
        config = frappe.conf.get('shared_bench_config', {})
        virtual_server = config.get('virtual_server_name', 'shared-bench-server')
        
        # Ensure the virtual server exists
        if not frappe.db.exists("Server", virtual_server):
            # Create or get the virtual server
            from press.press.utils.virtual_server import ensure_virtual_server
            ensure_virtual_server()
        
        # Assign the virtual server
        site.server = virtual_server
    
    @staticmethod
    def after_insert(site):
        """
        Called after inserting a new site.
        
        In shared bench mode:
        - Directly create site via Kubernetes exec (no agent job queuing)
        """
        if not is_shared_bench_mode():
            return
        
        # Get the shared bench agent
        from press.press.utils.shared_bench_agent import SharedBenchAgent
        agent = SharedBenchAgent()
        
        # Create the site synchronously
        try:
            job = agent.new_site(site)
            
            if job.status == "Success":
                frappe.db.set_value("Site", site.name, "status", "Active")
                frappe.msgprint(f"Site {site.name} created successfully!")
            else:
                frappe.db.set_value("Site", site.name, "status", "Broken")
                frappe.throw(f"Site creation failed: {job.error}")
                
        except Exception as e:
            frappe.db.set_value("Site", site.name, "status", "Broken")
            frappe.log_error(f"Failed to create site {site.name}: {e}")
            frappe.throw(f"Site creation failed: {e}")
    
    @staticmethod
    def on_update(site):
        """Called when site is updated"""
        if not is_shared_bench_mode():
            return
        
        # Handle config updates
        if site.has_value_changed("config"):
            from press.press.utils.shared_bench_agent import SharedBenchAgent
            agent = SharedBenchAgent()
            agent.update_site_config(site)
    
    @staticmethod
    def before_archive(site):
        """
        Called before archiving a site.
        
        In shared bench mode:
        - Take final backup
        - Drop site from shared bench
        """
        if not is_shared_bench_mode():
            return
        
        from press.press.utils.shared_bench_agent import SharedBenchAgent
        agent = SharedBenchAgent()
        
        # Archive the site
        job = agent.archive_site(site)
        
        if job.status != "Success":
            frappe.throw(f"Failed to archive site: {job.error}")


def install_hooks():
    """
    Install shared bench hooks into the Site doctype.
    
    Call this from hooks.py or during app setup.
    """
    if not is_shared_bench_mode():
        return
    
    # Add controller hooks
    from press.press.doctype.site.site import Site
    
    # Store original methods
    original_before_insert = getattr(Site, 'before_insert', None)
    original_after_insert = getattr(Site, 'after_insert', None)
    original_on_update = getattr(Site, 'on_update', None)
    
    def patched_before_insert(self):
        SharedBenchSiteController.before_insert(self)
        if original_before_insert:
            original_before_insert(self)
    
    def patched_after_insert(self):
        SharedBenchSiteController.after_insert(self)
        if original_after_insert:
            original_after_insert(self)
    
    def patched_on_update(self):
        SharedBenchSiteController.on_update(self)
        if original_on_update:
            original_on_update(self)
    
    Site.before_insert = patched_before_insert
    Site.after_insert = patched_after_insert
    Site.on_update = patched_on_update
    
    frappe.logger().info("Shared bench hooks installed for Site doctype")
