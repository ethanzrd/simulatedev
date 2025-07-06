#!/usr/bin/env python3
"""
OpenAI Codex Web Agent Implementation

Simplified and maintainable implementation for accessing OpenAI Codex.
Core flow: Login → Environments → Repository Selection → Task Execution → PR Creation
"""

import re
import time
from typing import Optional, Tuple
from .web_agent import WebAgent, AgentResponse


# Selector constants for better maintainability
class CodexSelectors:
    # Authentication (PROVEN WORKING)
    LOGIN_BUTTON = "button[data-testid='login-button']"
    GOOGLE_BUTTON = "button:has-text('Continue with Google')"
    
    # Input and submission (PROVEN WORKING)
    PROMPT_INPUT = "#prompt-textarea"
    CODE_BUTTON = "button:has-text('Code')"
    CHAT_INPUT = "#prompt-textarea"  # Same as prompt input, placeholder check failed
    
    # Environment management (PROVEN WORKING)
    USE_THIS_BUTTON = "button:has-text('Use this')"
    CREATE_ENV_BUTTON = "button.btn-primary"  # Simple version worked, complex one failed
    
    # Repository selection (PROVEN WORKING)
    EXISTING_REPO_ROW = "tr.group\\/row:has-text('{repo_name}')"  # For existing environments
    NEW_REPO_BUTTON = "button:has(p.text-token-text-primary.text-start.text-sm.font-medium:text('{repo_name}'))"  # For new environments
    FINAL_CREATE_BUTTON = "div.flex.items-center.justify-center:text('Create environment')"  # Final create step
    REPO_LIST_CONTAINER = ".flex.max-h-56.flex-col.overflow-y-auto"  # Creation list container
    REPO_NAME_ELEMENTS = "button p.text-token-text-primary"  # For verification
    
    # Task and PR management (PROVEN WORKING)
    TASK_LINK = ".task-row-container a"
    STOP_BUTTON = "button[aria-label='stop-button'], button[data-testid='stop-button']"
    CREATE_PR_BUTTON = "div.btn-primary button:has(span:text('Create PR'))"
    VIEW_PR_LINK = "a:has(span:text('View PR'))"
    
    # Output content extraction (NEW)
    OUTPUT_CONTENT = "div.markdown.prose, div[class*='markdown'][class*='prose']"
    
    # Loading and status (PROVEN WORKING)
    LOADING = ".animate-pulse, .loading, [role='progressbar']"


class OpenAICodexAgent(WebAgent):
    """Simplified OpenAI Codex web agent"""
    
    def __init__(self, computer_use_client):
        super().__init__(computer_use_client)
    
    @property
    def web_url(self) -> str:
        return "https://chatgpt.com/auth/login?next=/codex/settings/environments"
    
    @property
    def input_selector(self) -> str:
        return CodexSelectors.PROMPT_INPUT
    
    @property
    def submit_selector(self) -> str:
        return CodexSelectors.CODE_BUTTON
    
    @property
    def output_selector(self) -> str:
        return CodexSelectors.TASK_LINK
    
    @property
    def loading_selector(self) -> Optional[str]:
        return CodexSelectors.LOADING

    # =============================================================================
    # CORE FLOW METHODS
    # =============================================================================

    async def _setup_web_interface(self) -> bool:
        """Main setup flow: authenticate and navigate to correct environment"""
        try:
            print("Starting OpenAI Codex setup...")
            
            # Step 1: Handle authentication if needed
            if not await self._handle_authentication():
                return False
            
            # Step 2: Handle environments page
            if not await self._handle_environments_page():
                return False
            
            print("SUCCESS: OpenAI Codex setup completed successfully")
            return True
            
        except Exception as e:
            print(f"ERROR: Setup failed: {str(e)}")
            return False

    async def execute_prompt(self, prompt: str) -> AgentResponse:
        """Execute a coding task on OpenAI Codex"""
        try:
            print(f"Executing task: {prompt[:100]}...")
            
            # Send prompt and create task
            await self._send_prompt(prompt)
            
            # Open the created task
            if not await self._open_created_task():
                return AgentResponse(content="", success=False, error_message="Failed to open task")
            
            # Wait for completion and get output content and PR URL
            output_content, pr_url = await self._complete_task_and_get_pr()
            
            # Build response content
            response_parts = []
            
            if output_content:
                response_parts.append("AGENT OUTPUT:")
                response_parts.append("=" * 50)
                response_parts.append(output_content)
                response_parts.append("=" * 50)
            
            if pr_url:
                response_parts.append(f"PR created: {pr_url}")
                status_message = "Task completed successfully with output and PR created."
            elif output_content:
                status_message = "Task completed successfully with output generated."
            else:
                status_message = "Task completed but no output or PR captured."
            
            if response_parts:
                response_parts.insert(0, status_message)
                final_content = "\n\n".join(response_parts)
            else:
                final_content = status_message
            
            return AgentResponse(content=final_content, success=True)
            
        except Exception as e:
            return AgentResponse(content="", success=False, error_message=str(e))

    # =============================================================================
    # AUTHENTICATION FLOW
    # =============================================================================

    async def _handle_authentication(self) -> bool:
        """Handle the complete authentication flow"""
        current_url = self.page.url
        
        # Check if already authenticated
        if self._is_environments_page(current_url):
            return True
        
        # Handle login page
        if 'auth/login' in current_url or await self._is_login_page():
            print("Authenticating...")
            if not await self._click_element(CodexSelectors.LOGIN_BUTTON, "login button"):
                return False
            await self.page.wait_for_timeout(3000)
            current_url = self.page.url
        
        # Handle OpenAI auth page
        if 'auth.openai.com' in current_url:
            if not await self._click_element(CodexSelectors.GOOGLE_BUTTON, "Google login button"):
                return False
            await self.page.wait_for_timeout(3000)
            current_url = self.page.url
        
        # Handle Google authentication
        if 'accounts.google.com' in current_url:
            if not await self.handle_google_login():
                return False
            await self.page.wait_for_timeout(5000)
        
        # Verify we reached environments page
        return self._is_environments_page(self.page.url)

    async def _is_login_page(self) -> bool:
        """Check if we're on a login/signup page"""
        try:
            page_text = await self.page.content()
            return all(text in page_text for text in ["Get started", "Log in", "Sign up"])
        except:
            return False

    def _is_environments_page(self, url: str) -> bool:
        """Check if we're on the environments page"""
        return 'chatgpt.com/codex/settings/environment' in url

    # =============================================================================
    # ENVIRONMENTS AND REPOSITORY MANAGEMENT
    # =============================================================================

    async def _handle_environments_page(self) -> bool:
        """Handle environment selection or creation for the repository"""
        repo_url = self.get_working_repo_url()
        if not repo_url:
            print("WARNING: No repository URL provided")
            return True
        
        repo_name = self._extract_repo_name(repo_url)
        print(f"Setting up environment for repository: {repo_name}")
        
        # Check if we're already on environment creation page
        if 'settings/environment/create' in self.page.url:
            return await self._create_new_environment(repo_name)
        
        # Look for existing environment
        if await self._find_and_select_existing_environment(repo_name):
            print("Found and selected existing environment")
            return True
        
        # Create new environment
        print("Creating new environment...")
        if not await self._click_element(CodexSelectors.CREATE_ENV_BUTTON, "create environment button"):
            print("ERROR: Failed to click create environment button")
            return False
        
        return await self._create_new_environment(repo_name)

    async def _find_and_select_existing_environment(self, repo_name: str) -> bool:
        """Find and select an existing environment"""
        try:
            # Look for repository in environments table using proven selector
            repo_selector = CodexSelectors.EXISTING_REPO_ROW.format(repo_name=repo_name)
            
            # Wait for the table to load
            await self.page.wait_for_load_state("networkidle")
            
            element = await self._get_element_robust(repo_selector, f"existing environment for {repo_name}")
            
            if element:
                success = await self._robust_click_element(repo_selector, f"repository row for {repo_name}")
                if success:
                    # Wait for selection to process
                    await self.page.wait_for_timeout(2000)
                    return await self._robust_click_element(CodexSelectors.USE_THIS_BUTTON, "Use this button")
            
            return False
        except Exception as e:
            print(f"Error finding existing environment: {str(e)}")
            return False

    async def _create_new_environment(self, repo_name: str) -> bool:
        """Create a new environment by selecting repository"""
        try:
            # Wait for repository creation list to load
            await self._wait_for_element(CodexSelectors.REPO_LIST_CONTAINER, "creation list container")
            await self._wait_for_element(CodexSelectors.REPO_NAME_ELEMENTS, "repository list")
            await self.page.wait_for_timeout(2000)  # Allow list to fully populate
            
            # Wait for at least one repository button to become available
            await self.page.wait_for_selector("button p.text-token-text-primary", timeout=10000)
            
            # Find and click repository using proven selector
            repo_only = repo_name.split('/')[-1] if '/' in repo_name else repo_name
            repo_selector = CodexSelectors.NEW_REPO_BUTTON.format(repo_name=repo_only)
            
            element = await self.page.query_selector(repo_selector)
            
            if element and await element.is_visible():
                await self._scroll_and_click(element, f"repository {repo_only}")
            else:
                print(f"ERROR: Repository {repo_only} not found")
                return False
            
            # Click final create button using proven selector
            if self.page:
                await self.page.wait_for_timeout(2000)
            final_create_element = await self.page.query_selector(CodexSelectors.FINAL_CREATE_BUTTON)
            
            if final_create_element and await final_create_element.is_visible():
                await self._scroll_and_click(final_create_element, "final create environment button")
            else:
                print("ERROR: Failed to create environment")
                return False
            
            # Wait for redirect and click "Use this"
            await self._wait_for_redirect()
            return await self._click_element(CodexSelectors.USE_THIS_BUTTON, "Use this button")
            
        except Exception as e:
            print(f"ERROR: Failed to create environment: {str(e)}")
            return False

    async def _wait_for_redirect(self):
        """Wait for redirect to environment page"""
        await self.page.wait_for_timeout(3000)
        await self._wait_for_element(CodexSelectors.USE_THIS_BUTTON, "Use this button")

    def _extract_repo_name(self, repo_url: str) -> str:
        """Extract repository name from GitHub URL"""
        if not repo_url:
            return ""
        
        pattern = r'github\.com[/:]([\w\-\.]+)/([\w\-\.]+?)(?:\.git)?/?$'
        match = re.search(pattern, repo_url)
        
        if match:
            username, repo_name = match.groups()
            return f"{username}/{repo_name}"
        
        return ""

    # =============================================================================
    # TASK EXECUTION FLOW
    # =============================================================================

    async def _send_prompt(self, prompt: str):
        """Send prompt to the Codex interface"""
        
        success = await self._robust_fill_input(CodexSelectors.PROMPT_INPUT, prompt)
        if not success:
            raise Exception("Failed to fill prompt input")
        
        # Click Code button with robust method
        success = await self._robust_click_element(CodexSelectors.CODE_BUTTON, "Code button")
        if not success:
            raise Exception("Failed to click Code button")

    async def _open_created_task(self) -> bool:
        """Find and open the newly created task"""
        
        # Wait for loading to complete
        await self._wait_for_loading_complete()
        
        # Find and click task link
        await self.page.wait_for_timeout(3000)
        task_element = await self.page.query_selector(CodexSelectors.TASK_LINK)
        
        if task_element:
            href = await task_element.get_attribute('href')
            await task_element.click()
            await self.page.wait_for_timeout(2000)
            return True
        
        print("ERROR: No task found")
        return False

    async def _complete_task_and_get_pr(self) -> Tuple[Optional[str], Optional[str]]:
        """Wait for task completion and extract output content and PR URL"""
        
        # Focus on chat input
        await self._focus_chat_input()
        
        # Wait for completion (stop button disappears)
        await self._wait_for_completion()
        
        # Extract output content after completion
        output_content = await self._extract_output_content()
        
        # Try to create PR
        await self._try_create_pr()
        
        # Extract PR URL
        pr_url = await self._extract_pr_url()
        
        return output_content, pr_url

    async def _extract_output_content(self) -> Optional[str]:
        """Extract the agent's output content from the page"""
        try:
            # Wait a moment for content to fully render
            await self.page.wait_for_timeout(2000)
            
            # Try to find output content using the selector
            output_elements = await self.page.query_selector_all(CodexSelectors.OUTPUT_CONTENT)
            
            if not output_elements:
                print("WARNING: No output content found using primary selector")
                # Fallback: try to find any markdown content
                output_elements = await self.page.query_selector_all("div[class*='markdown'], div[class*='prose']")
            
            if output_elements:
                # Get the text content from the last (most recent) output element
                content_element = output_elements[-1]
                content = await content_element.inner_text()
                
                if content and len(content.strip()) > 0:
                    print(f"SUCCESS: Extracted {len(content)} characters of output content")
                    return content.strip()
                else:
                    print("WARNING: Output element found but no text content")
            else:
                print("WARNING: No output content elements found")
                
        except Exception as e:
            print(f"ERROR: Failed to extract output content: {str(e)}")
        
        return None

    async def _focus_chat_input(self):
        """Focus on the chat input field"""
        try:
            # Use proven chat input selector (same as prompt input)
            element = await self.page.query_selector(CodexSelectors.CHAT_INPUT)
            if element:
                await element.click()
                await self.page.wait_for_timeout(1000)
        except Exception as e:
            print(f"WARNING: Could not focus chat input: {str(e)}")

    async def _wait_for_completion(self):
        """Wait for task completion by monitoring stop button"""
        try:
            # Wait for stop button to appear with robust waiting
            stop_button_appeared = await self._wait_for_element_robust(
                CodexSelectors.STOP_BUTTON, 
                "stop button", 
                timeout=30000
            )
            
            if stop_button_appeared:
                # Wait for stop button to disappear (task completion)
                await self.page.wait_for_selector(
                    CodexSelectors.STOP_BUTTON, 
                    state="hidden", 
                    timeout=1200000
                )
                print("Stop button disappeared, task completed")
            else:
                print("WARNING: Stop button never appeared, task may have completed immediately")
            
        except Exception as e:
            print(f"WARNING: Could not monitor task completion: {str(e)}")
        
        # Wait for any final processing
        await self.page.wait_for_timeout(2000)

    async def _try_create_pr(self):
        """Try to click Create PR button if available"""
        try:
            await self.page.wait_for_selector(CodexSelectors.CREATE_PR_BUTTON, timeout=10000)
            element = await self.page.query_selector(CodexSelectors.CREATE_PR_BUTTON)
            
            if element and await element.is_visible():
                await element.click()
                await self.page.wait_for_timeout(3000)
            
        except:
            pass  # No Create PR button found

    async def _extract_pr_url(self) -> Optional[str]:
        """Extract PR URL from View PR button"""
        
        try:
            await self.page.wait_for_selector(CodexSelectors.VIEW_PR_LINK, timeout=30000)
            pr_link = await self.page.query_selector(CodexSelectors.VIEW_PR_LINK)
            
            if pr_link:
                href = await pr_link.get_attribute('href')
                if href and 'github.com' in href and '/pull/' in href:
                    return href
                    
        except Exception as e:
            print(f"WARNING: No PR URL found: {str(e)}")
        
        return None

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================

    async def _wait_for_element(self, selector: str, description: str, timeout: int = 10000):
        """Wait for an element to appear"""
        return await self._wait_for_element_robust(selector, description, timeout)

    async def _click_element(self, selector: str, description: str) -> bool:
        """Find and click an element"""
        return await self._robust_click_element(selector, description)

    async def _scroll_and_click(self, element, description: str):
        """Scroll element into view and click it"""
        try:
            await element.scroll_into_view_if_needed()
            
            # Wait for element to be stable
            await self.page.wait_for_timeout(self.config.ELEMENT_STABILITY_TIMEOUT)
            
            if await element.is_visible() and await element.is_enabled():
                try:
                    await element.click()
                    print(f"Successfully clicked {description}")
                except Exception:
                    # Fallback to JavaScript click
                    await element.evaluate("element => element.click()")
                    print(f"Successfully clicked {description} using JavaScript fallback")
            else:
                raise Exception(f"Element {description} not actionable after scrolling")
                
        except Exception as e:
            print(f"ERROR: Failed to click {description}: {str(e)}")

    async def _wait_for_loading_complete(self):
        """Wait for any loading indicators to complete"""
        try:
            # Check if loading indicator appears
            loading_appeared = await self._wait_for_element_robust(
                CodexSelectors.LOADING, 
                "loading indicator", 
                timeout=5000
            )
            
            if loading_appeared:
                # Wait for loading to complete
                await self.page.wait_for_selector(
                    CodexSelectors.LOADING, 
                    state="hidden", 
                    timeout=30000
                )
                print("Loading completed")
            else:
                print("No loading indicator found, assuming already loaded")
                
        except Exception as e:
            print(f"Loading check completed with warning: {str(e)}")   