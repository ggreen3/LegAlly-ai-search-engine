import websocket
import json
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import uuid
import tkinter as tk
from tkinter import ttk, scrolledtext
from concurrent.futures import ThreadPoolExecutor

class AISearchApp:
    def __init__(self):
        self.chat_id = str(uuid.uuid4())
        self.receiving = False
        self.driver = None
        self.search_history = []  # Store search results for follow-ups
        self.setup_browser()
        self.setup_gui()
        
    def setup_browser(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        self.driver = webdriver.Chrome(options=options)
        
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Advanced AI Search Assistant")
        self.root.geometry("1000x800")
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Search frame
        search_frame = ttk.Frame(main_frame)
        search_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.search_entry = ttk.Entry(search_frame, width=70)
        self.search_entry.grid(row=0, column=0, padx=(0, 10))
        
        search_button = ttk.Button(search_frame, text="Search", command=self.perform_search)
        search_button.grid(row=0, column=1, padx=(0, 10))
        
        # Number of sources selector
        ttk.Label(search_frame, text="Sources:").grid(row=0, column=2)
        self.sources_var = tk.StringVar(value="5")
        sources_spinner = ttk.Spinbox(search_frame, from_=1, to=10, width=5, textvariable=self.sources_var)
        sources_spinner.grid(row=0, column=3, padx=10)
        
        # Chat display
        self.chat_display = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=35)
        self.chat_display.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Follow-up frame
        followup_frame = ttk.Frame(main_frame)
        followup_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=10)
        
        self.followup_entry = ttk.Entry(followup_frame, width=70)
        self.followup_entry.grid(row=0, column=0, padx=(0, 10))
        
        followup_button = ttk.Button(followup_frame, text="Ask Follow-up", command=self.send_followup)
        followup_button.grid(row=0, column=1)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        search_frame.columnconfigure(0, weight=1)
        followup_frame.columnconfigure(0, weight=1)
        
        # Bind Enter keys
        self.search_entry.bind('<Return>', lambda e: self.perform_search())
        self.followup_entry.bind('<Return>', lambda e: self.send_followup())

    def extract_content_from_url(self, url):
        try:
            self.driver.get(url)
            time.sleep(2)  # Give JavaScript time to load
            
            # Parse content
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Remove scripts, styles, and nav elements
            for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
                element.decompose()
                
            # Extract text
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return {
                'url': url,
                'content': text[:4500],  # First 3000 chars for summary
                'title': soup.title.string if soup.title else 'No title'
            }
            
        except Exception as e:
            self.append_to_chat(f"❌ Error extracting content from {url}: {str(e)}\n")
            return None

    def search_google(self, query):
        try:
            num_sources = int(self.sources_var.get())
            self.append_to_chat(f"🔍 Searching Google for: {query}\nAnalyzing {num_sources} sources...\n\n")
            
            # Navigate to Google and search
            self.driver.get("https://www.google.com")
            wait = WebDriverWait(self.driver, 10)
            search_box = wait.until(EC.presence_of_element_located((By.NAME, "q")))
            search_box.send_keys(query)
            search_box.send_keys(Keys.RETURN)
            
            # Get multiple results
            results = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.g a")))
            urls = []
            for result in results[:num_sources]:
                url = result.get_attribute('href')
                if url and 'google.com' not in url:  # Filter out Google-related links
                    urls.append(url)
            
            # Extract content from all URLs in parallel
            with ThreadPoolExecutor(max_workers=10) as executor:
                contents = list(executor.map(self.extract_content_from_url, urls[:num_sources]))
            
            # Filter out None results and store in search history
            valid_contents = [c for c in contents if c is not None]
            self.search_history = valid_contents
            
            return valid_contents
            
        except Exception as e:
            self.append_to_chat(f"❌ Error during search: {str(e)}\n")
            return None

    def connect_websocket(self, message, is_followup=False):
        def on_message(ws, message):
            self.append_to_chat(message)

        def on_error(ws, error):
            self.append_to_chat(f"❌ WebSocket error: {error}\n")
            self.receiving = False

        def on_close(ws, close_status_code, close_msg):
            self.receiving = False
            if not is_followup:
                self.append_to_chat("\n\n💡 You can ask follow-up questions below for more detailed information.\n")

        def on_open(ws):
            system_prompt = """You are an advanced research assistant. Your role is to:
1. Analyze multiple sources of information
2. Identify common themes and agreements across sources
3. Note any significant disagreements or unique perspectives
4. Synthesize a comprehensive answer based on the consensus
5. Highlight any limitations or areas where more research might be needed
6. For follow-up questions, provide more detailed analysis and explore specific aspects
Be thorough and analytical while maintaining clarity and readability."""
            
            ws.send(json.dumps({
                "chatId": self.chat_id,
                "appId": "after-consumer",
                "systemPrompt": system_prompt,
                "message": message
            }))

        websocket.enableTrace(True)
        ws = websocket.WebSocketApp(
            "wss://backend.buildpicoapps.com/api/chatbot/chat",
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        self.receiving = True
        ws.run_forever()

    def perform_search(self):
        query = self.search_entry.get().strip()
        if query and not self.receiving:
            self.search_entry.delete(0, tk.END)
            
            def search_thread():
                # Perform multi-source search
                results = self.search_google(query)
                if results:
                    # Format message for AI
                    ai_message = f"""Search query: {query}

Analyzing {len(results)} sources:

{'-' * 50}
"""
                    for i, result in enumerate(results, 1):
                        ai_message += f"""
Source {i}: {result['url']}

{result['content']}

{'-' * 50}
"""
                    
                    ai_message += """
Please analyze these sources and provide:
1. Key points of agreement across sources
2. Any significant disagreements
3. A comprehensive synthesis of the information
4. Areas where the information might be incomplete"""

                    # Connect to AI
                    self.append_to_chat("\n🤖 Analyzing multiple sources...\n\n")
                    self.connect_websocket(ai_message)
            
            threading.Thread(target=search_thread, daemon=True).start()

    def send_followup(self):
        followup = self.followup_entry.get().strip()
        if followup and not self.receiving and self.search_history:
            self.followup_entry.delete(0, tk.END)
            
            # Format follow-up message with context
            context_message = f"""Follow-up question: {followup}

Based on these previously analyzed sources:

{'-' * 50}
"""
            for i, result in enumerate(self.search_history, 1):
                context_message += f"""
Source {i}: {result['url']}

{result['content'][:1000]}  # Shortened for follow-up

{'-' * 50}
"""
            
            context_message += "\nPlease provide a detailed answer to the follow-up question using this context."
            
            self.append_to_chat(f"\n👤 Follow-up: {followup}\n\n")
            
            # Start new thread for AI processing
            threading.Thread(
                target=lambda: self.connect_websocket(context_message, True),
                daemon=True
            ).start()

    def append_to_chat(self, message):
        self.chat_display.insert(tk.END, message)
        self.chat_display.see(tk.END)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    app = AISearchApp()
    app.run()
