#!/usr/bin/env python3
"""
Web Agent Base Class Implementation

This module provides a base class for web-based coding agents that run in browsers.
Uses Botright for stealth browser automation and captcha solving.
"""

import asyncio
import time
import os
from abc import abstractmethod
from typing import Optional, Dict, Any, List
from .base import CodingAgent, AgentResponse
from common.exceptions import AgentTimeoutException
from common.config import config

import botright


class WebAutomationConfig:
    DEFAULT_TIMEOUT = 30000  # 30 seconds
    SHORT_TIMEOUT = 10000    # 10 seconds
    LONG_TIMEOUT = 60000     # 60 seconds
    RETRY_COUNT = 3
    RETRY_DELAY = 2000       # 2 seconds
    ELEMENT_STABILITY_TIMEOUT = 1000  # 1 second
    NETWORK_IDLE_TIMEOUT = 5000       # 5 seconds

# Selector constants for Google authentication
class GoogleSelectors:
    # Email input selectors
    EMAIL_INPUTS = [
        "input[type='email']",
        "#identifierId",
        "input[name='email']",
        "input[autocomplete='username']"
    ]
    
    # Email next/submit button selectors
    EMAIL_NEXT_BUTTONS = [
        "#identifierNext",
        "button:has-text('Next')",
        "input[type='submit']",
        "button[type='submit']"
    ]
    
    # Password input selectors
    PASSWORD_INPUTS = [
        "input[type='password']",
        "input[name='password']",
        "#password",
        "input[autocomplete='current-password']"
    ]
    
    # Password next/submit button selectors
    PASSWORD_NEXT_BUTTONS = [
        "#passwordNext",
        "button:has-text('Next')",
        "input[type='submit']",
        "button[type='submit']"
    ]


class WebAgent(CodingAgent):
    """Base class for web-based coding agents using Botright"""
    
    def __init__(self, computer_use_client):
        super().__init__(computer_use_client)
        self.botright_client = None
        self.browser = None
        self.page = None
        self._is_browser_ready = False
        self.config = WebAutomationConfig()
    
    @property
    def window_name(self) -> str:
        """Web agents don't have traditional windows, but we keep this for compatibility"""
        return f"{self.agent_name}_browser"
    
    @property
    @abstractmethod
    def web_url(self) -> str:
        """The URL of the web-based coding agent"""
        pass
    
    @property
    @abstractmethod
    def input_selector(self) -> str:
        """CSS selector for the input field where prompts are entered"""
        pass
    
    @property
    @abstractmethod
    def submit_selector(self) -> str:
        """CSS selector for the submit button"""
        pass
    
    @property
    @abstractmethod
    def output_selector(self) -> str:
        """CSS selector for the output/response area"""
        pass
    
    @property
    @abstractmethod
    def loading_selector(self) -> Optional[str]:
        """CSS selector for loading indicator (optional)"""
        pass
    
    @property
    def interface_state_prompt(self) -> str:
        """Not used for web agents, but kept for compatibility"""
        return ""
    
    @property
    def resume_button_prompt(self) -> str:
        """Not used for web agents, but kept for compatibility"""
        return ""
    
    @property
    def input_field_prompt(self) -> str:
        """Not used for web agents, but kept for compatibility"""
        return ""
    
    def set_current_project(self, project_path: str):
        """Override to handle web agent project context"""
        super().set_current_project(project_path)
        # Web agents might need to navigate to project-specific URLs or set context
        # This can be customized by subclasses
    
    def set_repository_context(self, repo_url: str, original_repo_url: Optional[str] = None):
        """Set repository context for web agents
        
        Args:
            repo_url: The repository URL the agent should work with (may be a fork)
            original_repo_url: The original repository URL (if repo_url is a fork)
        """
        self.repo_url = repo_url
        self.original_repo_url = original_repo_url
    
    def get_working_repo_url(self) -> Optional[str]:
        """Get the repository URL the agent should work with"""
        return getattr(self, 'repo_url', None)
    
    def get_original_repo_url(self) -> Optional[str]:
        """Get the original repository URL (before any forking)"""
        return getattr(self, 'original_repo_url', None)
    
    def is_ide_open_with_correct_project(self) -> bool:
        """Check if browser is open with the correct context"""
        if not self._current_project_name:
            return self._is_browser_ready
        
        # For web agents, we consider the project "correct" if the browser is ready
        # and we're on the right URL. Subclasses can override for more specific checks.
        return self._is_browser_ready and self.page is not None
    
    async def is_coding_agent_open(self) -> bool:
        """Check if the browser is open and ready"""
        try:
            return self._is_browser_ready and self.page is not None
                
        except Exception as e:
            return False
    
    async def is_coding_agent_open_with_project(self) -> bool:
        """Check if the browser is open and ready with correct project context"""
        if not await self.is_coding_agent_open():
            return False
            
        if not self.is_ide_open_with_correct_project():
            return False
            
        return True
    
    async def open_coding_interface(self) -> bool:
        """Open the web browser and navigate to the coding agent's website"""
        try:
            print(f"Opening {self.agent_name} web interface...")
            
            # Initialize Botright client if not already done
            if not self.botright_client:
                self.botright_client = await botright.Botright(
                    headless=False,  # Keep visible for debugging, can be made configurable
                    user_action_layer=True,  # Show what the bot is doing
                    mask_fingerprint=True,  # Enable stealth mode
                    spoof_canvas=True,  # Spoof canvas fingerprinting
                    scroll_into_view=True,  # Scroll into view
                )
            
            # Create new browser if not already done
            if not self.browser:
                self.browser = await self.botright_client.new_browser(no_viewport=True)
                
            # Create new page
            self.page = await self.browser.new_page()
            
            self.page.set_default_timeout(self.config.DEFAULT_TIMEOUT)
            self.page.set_default_navigation_timeout(self.config.LONG_TIMEOUT)
            
            # Navigate to the web agent URL with retry
            navigation_success = await self._robust_navigate(self.web_url)
            if not navigation_success:
                print(f"ERROR: Failed to navigate to {self.web_url}")
                return False
            
            # Perform any agent-specific setup
            setup_success = await self._setup_web_interface()
            if not setup_success:
                print(f"ERROR: Failed to setup {self.agent_name} web interface")
                return False
            
            self._is_browser_ready = True
            print(f"SUCCESS: {self.agent_name} web interface is ready")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to open {self.agent_name} web interface: {str(e)}")
            await self._cleanup_browser()
            return False
    
    async def close_coding_interface(self) -> bool:
        """Close the web browser"""
        try:
            await self._cleanup_browser()
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to close {self.agent_name} web interface: {str(e)}")
            return False
    
    async def _cleanup_browser(self):
        """Clean up browser resources"""
        try:
            self._is_browser_ready = False
            
            if self.page:
                await self.page.close()
                self.page = None
                
            if self.browser:
                await self.browser.close()
                self.browser = None
                
            if self.botright_client:
                await self.botright_client.close()
                self.botright_client = None
                
        except Exception as e:
            print(f"WARNING: Error during browser cleanup: {str(e)}")
    
    async def _setup_web_interface(self) -> bool:
        """Perform agent-specific setup after navigation. Override in subclasses."""
        # Default implementation - subclasses can override for specific setup
        try:
            # Solve any captchas that might appear
            await self.solve_captcha_if_present()
            
            # Wait for input field to be available with robust waiting
            input_available = await self._wait_for_element_robust(
                self.input_selector, 
                "input field",
                timeout=self.config.DEFAULT_TIMEOUT
            )
            
            if not input_available:
                print(f"ERROR: Could not find input field for {self.agent_name}")
                return False
                
            return True
        except Exception as e:
            print(f"ERROR: Setup failed for {self.agent_name}: {str(e)}")
            return False
    
    async def execute_prompt(self, prompt: str) -> AgentResponse:
        """Execute prompt by sending it to the web interface"""
        try:
            if not self._is_browser_ready or not self.page:
                raise Exception("Browser not ready. Call open_coding_interface() first.")
            
            print(f"Executing task: {prompt[:100]}...")
            
            # Combine prompt with instruction to save output
            combined_prompt = f"""{prompt}\n\nAfter completing the above task, please save a comprehensive summary of everything you did to a file called '{self.output_file}' in the current directory. Include:\n- All changes made\n- Explanations of what was done.\n\nIMPORTANT: Do NOT create or update any documentation files (such as README.md or docs/*) unless you are explicitly asked to do so in the original prompt. If you believe that creating a documentation file would help you better implement the required coding task, you may create it, but you must delete it once you are finished and before you finish the task."""
            
            # Send prompt to web interface
            await self._send_prompt_to_web_interface(combined_prompt)
            
            # Wait for completion
            await self._wait_for_web_completion()
            
            # Read output file
            content = await self._read_output_file()
            
            return AgentResponse(content=content, success=True)
            
        except Exception as e:
            return AgentResponse(
                content="",
                success=False,
                error_message=f"Failed to execute prompt: {str(e)}"
            )
    
    async def _send_prompt_to_web_interface(self, prompt: str):
        """Send prompt to the web interface"""
        try:
            success = await self._robust_fill_input(self.input_selector, prompt)
            if not success:
                raise Exception("Failed to fill input field")
            
            success = await self._robust_click_element(self.submit_selector, "submit button")
            if not success:
                raise Exception("Failed to click submit button")
            
            # Wait for submission to be processed
            if self.page:
                await self.page.wait_for_timeout(self.config.RETRY_DELAY)
            
        except Exception as e:
            raise Exception(f"Failed to send prompt to web interface: {str(e)}")
    
    async def _wait_for_web_completion(self):
        """Wait for the web agent to complete processing"""
        timeout_seconds = config.agent_timeout_seconds
        timeout_ms = timeout_seconds * 1000
        
        try:
            # Check if loading indicator is present (if defined)
            if self.loading_selector and self.page:
                try:
                    # Wait for loading indicator to disappear
                    await self.page.wait_for_selector(
                        self.loading_selector, 
                        state="hidden", 
                        timeout=timeout_ms
                    )
                    print("Loading indicator disappeared, task likely completed")
                    return
                except Exception as e:
                    print(f"Loading indicator check failed, trying alternative methods: {str(e)}")
            
            await self._monitor_output_changes(timeout_ms)
                
        except Exception as e:
            if isinstance(e, AgentTimeoutException):
                raise
            else:
                print(f"WARNING: Error waiting for completion, assuming done: {str(e)}")
    
    async def get_web_output(self) -> str:
        """Extract output from the web interface. Override in subclasses for specific parsing."""
        try:
            if not self.page:
                return ""
            
            # Try to get output from the designated output selector with robust waiting
            output_element = await self._get_element_robust(self.output_selector, "output area")
            if output_element:
                return await output_element.text_content() or ""
            
            return ""
            
        except Exception as e:
            print(f"WARNING: Could not extract output from web interface: {str(e)}")
            return ""
    
    async def handle_google_login(self) -> bool:
        """Handle Google authentication using environment variables
        
        Assumes we're already on the Google login page.
        Uses GOOGLE_EMAIL and GOOGLE_PASSWORD environment variables.
        
        Returns:
            bool: True if login was successful, False if login failed
        """
        try:
            # Get credentials from environment variables
            google_email = os.getenv('GOOGLE_EMAIL')
            google_password = os.getenv('GOOGLE_PASSWORD')
            
            if not google_email or not google_password:
                print("ERROR: GOOGLE_EMAIL or GOOGLE_PASSWORD environment variables not set")
                return False
            
            # Wait for Google login page to be ready
            if self.page:
                await self.page.wait_for_load_state("networkidle")
            
            # Handle email input with robust selector fallback
            email_success = await self._robust_fill_input_from_selectors(
                GoogleSelectors.EMAIL_INPUTS, 
                google_email, 
                "email input"
            )
            
            if email_success:
                # Click Next or submit button for email
                next_success = await self._robust_click_from_selectors(
                    GoogleSelectors.EMAIL_NEXT_BUTTONS,
                    "email next button"
                )
                
                if next_success and self.page:
                    # Wait for password page to load
                    await self.page.wait_for_load_state("networkidle")
            
            # Handle password input with robust selector fallback
            password_success = await self._robust_fill_input_from_selectors(
                GoogleSelectors.PASSWORD_INPUTS,
                google_password,
                "password input"
            )
            
            if password_success:
                # Click Next or submit button for password
                submit_success = await self._robust_click_from_selectors(
                    GoogleSelectors.PASSWORD_NEXT_BUTTONS,
                    "password next button"
                )
                
                if submit_success:
                    # Wait for login to complete with robust URL monitoring
                    return await self._wait_for_login_completion()
            
            print("ERROR: Failed to complete Google login flow")
            return False
                
        except Exception as e:
            print(f"ERROR: Google login failed: {str(e)}")
            return False

    async def solve_captcha_if_present(self) -> bool:
        """Use Botright's captcha solving capabilities if a captcha is detected"""
        try:
            # Check for common captcha types and solve them using Botright
            # This is a basic implementation - subclasses can override for specific captcha handling
            
            if not self.page:
                print("Page not available for captcha solving")
                return False
                
            captcha_types = [
                ("hCaptcha", self.page.solve_hcaptcha),
                ("reCaptcha", self.page.solve_recaptcha),
                ("geeTest", self.page.solve_geetest)
            ]
            
            for captcha_name, solve_method in captcha_types:
                try:
                    print(f"Attempting to solve {captcha_name}...")
                    await solve_method()
                    print(f"Successfully solved {captcha_name}")
                    return True
                except Exception as e:
                    print(f"No {captcha_name} found or failed to solve: {str(e)}")
                    continue
            
            return False
            
        except Exception as e:
            print(f"WARNING: Error during captcha solving: {str(e)}")
            return False
    
    
    async def _robust_navigate(self, url: str, max_retries: Optional[int] = None) -> bool:
        """Navigate to URL with retry logic"""
        max_retries = max_retries or self.config.RETRY_COUNT
        
        if not self.page:
            print("Page not available for navigation")
            return False
        
        for attempt in range(max_retries):
            try:
                print(f"Navigating to {url} (attempt {attempt + 1}/{max_retries})")
                await self.page.goto(url, wait_until="networkidle", timeout=self.config.LONG_TIMEOUT)
                return True
            except Exception as e:
                print(f"Navigation attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1 and self.page:
                    await self.page.wait_for_timeout(self.config.RETRY_DELAY)
                else:
                    print(f"Failed to navigate to {url} after {max_retries} attempts")
                    return False
        return False
    
    async def _wait_for_element_robust(self, selector: str, description: str, timeout: Optional[int] = None, state: str = "visible") -> bool:
        """Wait for element with robust error handling"""
        timeout = timeout or self.config.DEFAULT_TIMEOUT
        
        try:
            if not self.page:
                print(f"Page not available for waiting for {description}")
                return False
                
            await self.page.wait_for_selector(selector, state=state, timeout=timeout)
            print(f"Successfully found {description}")
            return True
        except Exception as e:
            print(f"Failed to find {description} with selector '{selector}': {str(e)}")
            return False
    
    async def _get_element_robust(self, selector: str, description: str, timeout: Optional[int] = None):
        """Get element with robust waiting and error handling"""
        timeout = timeout or self.config.DEFAULT_TIMEOUT
        
        try:
            if not self.page:
                print(f"Page not available for getting {description}")
                return None
                
            await self.page.wait_for_selector(selector, timeout=timeout)
            
            element = await self.page.query_selector(selector)
            if element:
                return element
            else:
                print(f"Element {description} found but query_selector returned None")
                return None
        except Exception as e:
            print(f"Failed to get {description}: {str(e)}")
            return None
    
    async def _robust_click_element(self, selector: str, description: str, max_retries: Optional[int] = None) -> bool:
        """Click element with retry logic and actionability checks"""
        max_retries = max_retries or self.config.RETRY_COUNT
        
        for attempt in range(max_retries):
            try:
                if not self.page:
                    raise Exception("Page not available")
                    
                # Wait for element to be present and visible
                await self.page.wait_for_selector(selector, state="visible", timeout=self.config.DEFAULT_TIMEOUT)
                
                element = await self.page.query_selector(selector)
                if not element:
                    raise Exception(f"Element not found: {selector}")
                
                # Check if element is actionable
                if await element.is_visible() and await element.is_enabled():
                    await element.scroll_into_view_if_needed()
                    
                    # Wait for element to be stable
                    if self.page:
                        await self.page.wait_for_timeout(self.config.ELEMENT_STABILITY_TIMEOUT)
                    
                    await element.click()
                    print(f"Successfully clicked {description}")
                    return True
                else:
                    raise Exception(f"Element not actionable: {description}")
                    
            except Exception as e:
                print(f"Click attempt {attempt + 1} failed for {description}: {str(e)}")
                if attempt < max_retries - 1 and self.page:
                    await self.page.wait_for_timeout(self.config.RETRY_DELAY)
                else:
                    print(f"Failed to click {description} after {max_retries} attempts")
                    return False
        return False
    
    async def _robust_fill_input(self, selector: str, text: str, max_retries: Optional[int] = None) -> bool:
        """Fill input field with retry logic and proper clearing"""
        max_retries = max_retries or self.config.RETRY_COUNT
        
        for attempt in range(max_retries):
            try:
                if not self.page:
                    raise Exception("Page not available")
                    
                # Wait for input to be present and visible
                await self.page.wait_for_selector(selector, state="visible", timeout=self.config.DEFAULT_TIMEOUT)
                
                input_element = await self.page.query_selector(selector)
                if not input_element:
                    raise Exception(f"Input element not found: {selector}")
                
                # Check if element is actionable
                if await input_element.is_visible() and await input_element.is_enabled():
                    # Focus on the input
                    await input_element.focus()
                    
                    # Clear existing content
                    await input_element.select_text()
                    if self.page:
                        await self.page.keyboard.press("Delete")
                    
                    await input_element.fill(text)
                    
                    current_value = await input_element.input_value()
                    if current_value == text:
                        print(f"Successfully filled input with text (length: {len(text)})")
                        return True
                    else:
                        raise Exception(f"Text verification failed. Expected: {text[:50]}..., Got: {current_value[:50]}...")
                else:
                    raise Exception("Input element not actionable")
                    
            except Exception as e:
                print(f"Fill attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1 and self.page:
                    await self.page.wait_for_timeout(self.config.RETRY_DELAY)
                else:
                    print(f"Failed to fill input after {max_retries} attempts")
                    return False
        return False
    
    async def _robust_fill_input_from_selectors(self, selectors: List[str], text: str, description: str) -> bool:
        """Try multiple selectors to fill input field"""
        for selector in selectors:
            try:
                if not self.page:
                    continue
                    
                # Check if this selector exists
                element = await self.page.query_selector(selector)
                if element and await element.is_visible():
                    success = await self._robust_fill_input(selector, text)
                    if success:
                        print(f"Successfully filled {description} using selector: {selector}")
                        return True
            except Exception as e:
                print(f"Selector {selector} failed for {description}: {str(e)}")
                continue
        
        print(f"Failed to fill {description} with any of the provided selectors")
        return False
    
    async def _robust_click_from_selectors(self, selectors: List[str], description: str) -> bool:
        """Try multiple selectors to click element"""
        for selector in selectors:
            try:
                if not self.page:
                    continue
                    
                # Check if this selector exists
                element = await self.page.query_selector(selector)
                if element and await element.is_visible() and await element.is_enabled():
                    success = await self._robust_click_element(selector, description)
                    if success:
                        print(f"Successfully clicked {description} using selector: {selector}")
                        return True
            except Exception as e:
                print(f"Selector {selector} failed for {description}: {str(e)}")
                continue
        
        print(f"Failed to click {description} with any of the provided selectors")
        return False
    
    async def _wait_for_login_completion(self, max_wait_seconds: int = 300) -> bool:
        """Wait for login to complete by monitoring URL changes"""
        poll_interval_ms = 5000  # 5 seconds
        elapsed_ms = 0
        max_wait_ms = max_wait_seconds * 1000
        
        if not self.page:
            print("Page not available for login completion check")
            return False
        
        try:
            while elapsed_ms < max_wait_ms:
                await self.page.wait_for_timeout(poll_interval_ms)
                elapsed_ms += poll_interval_ms
                
                current_url = self.page.url
                if 'accounts.google.com' not in current_url:
                    print("Login completed successfully")
                    return True
                    
                print(f"Still on Google login page, waiting... ({elapsed_ms/1000}s elapsed)")
            
            print("Login verification timed out")
            return False
            
        except Exception as e:
            print(f"Error waiting for login completion: {str(e)}")
            return False
    
    async def _monitor_output_changes(self, timeout_ms: int):
        """Monitor output area for content changes to detect completion"""
        check_interval_ms = 5000  # 5 seconds
        stable_content_duration_ms = 10000  # 10 seconds of stable content
        
        last_content = ""
        last_change_time = time.time() * 1000
        start_time = time.time() * 1000
        
        while (time.time() * 1000) - start_time < timeout_ms:
            try:
                output_element = None
                if self.page:
                    output_element = await self.page.query_selector(self.output_selector)
                current_content = ""
                if output_element:
                    current_content = await output_element.text_content() or ""
                
                # Check if content has changed
                if current_content != last_content:
                    last_content = current_content
                    last_change_time = time.time() * 1000
                    print(f"Output content changed (length: {len(current_content)})")
                
                # Check if content has been stable for the required duration
                current_time = time.time() * 1000
                if (current_time - last_change_time) >= stable_content_duration_ms and len(current_content) > 100:
                    print("Output content appears stable, assuming completion")
                    return
                
                # Wait before next check
                if self.page:
                    await self.page.wait_for_timeout(check_interval_ms)
                
            except Exception as e:
                print(f"Error monitoring output changes: {str(e)}")
                if self.page:
                    await self.page.wait_for_timeout(check_interval_ms)
        
        timeout_seconds = int(timeout_ms / 1000)
        raise AgentTimeoutException(self.agent_name, timeout_seconds, "Web agent processing timed out")                