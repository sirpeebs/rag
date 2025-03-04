document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatLog = document.getElementById("chat-log");
  const sidebar = document.getElementById("sidebar");
  const toggleSidebarBtn = document.getElementById("toggleSidebar");
  const conversationsList = document.getElementById("conversationsList");
  const newChatBtn = document.getElementById("newChatBtn");
  
  // Active conversation holds the ongoing messages (each an object with role and content)
  let activeConversation = [];
  // Use a timestamp as a unique conversation ID for the current conversation
  let activeConversationId = Date.now();
  // Active machine model for the current conversation
  let activeModel = "";
  // Saved conversations stored by their unique id
  let savedConversations = {};
  // Flag to track if the active conversation has been modified
  let isConversationModified = false;
  // Flag to indicate if a conversation was loaded from storage
  let isResumed = false;
  
  // Toggle sidebar open/closed
  toggleSidebarBtn.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    const icon = toggleSidebarBtn.querySelector("i");
    if (sidebar.classList.contains("collapsed")) {
      icon.classList.remove("fa-chevron-left");
      icon.classList.add("fa-chevron-right");
    } else {
      icon.classList.remove("fa-chevron-right");
      icon.classList.add("fa-chevron-left");
    }
  });
  
  // "New Chat" saves the current conversation if it has been modified and clears the chat
  newChatBtn.addEventListener("click", () => {
    // Save current conversation if modified
    if (activeConversation.length > 0 && isConversationModified) {
      savedConversations[activeConversationId] = {model: activeModel, messages: activeConversation.slice()};
      addConversationToSidebar(activeConversationId, savedConversations[activeConversationId]);
    }
    // Prompt for machine model
    const model = prompt("Enter the machine model (e.g., VF-4):");
    if (!model) return;
    // Start new conversation
    activeModel = model;
    activeConversation = [];
    activeConversationId = Date.now();
    isConversationModified = false;
    isResumed = false;
    chatLog.innerHTML = "";
  });
  
  // Handle chat form submission
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;
    
    // If this conversation was resumed from a stored chat, then create a new conversation file for new messages
    if (isResumed) {
      activeConversationId = Date.now();
      isResumed = false;
    }
    // Append the user's message to the active conversation and display it
    activeConversation.push({ role: "user", content: message });
    appendMessage("user", message);
    chatInput.value = "";
    // Mark conversation as modified
    isConversationModified = true;
    
    try {
      // Send the model and conversation to the /chat endpoint
      const response = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: activeModel, conversation: activeConversation })
      });
      const data = await response.json();
      const reply = data.response;
      activeConversation.push({ role: "assistant", content: reply });
      appendMessage("assistant", reply);
      // If this conversation is already stored, update its snippet
      if (savedConversations.hasOwnProperty(activeConversationId)) {
        updateConversationInSidebar(activeConversationId, savedConversations[activeConversationId]);
      }
    } catch (error) {
      appendMessage("assistant", "Error: " + error.message);
    }
  });
  
  // Appends a single message to the chat log
  function appendMessage(sender, message) {
    const messageDiv = document.createElement("div");
    messageDiv.classList.add("chat-message", sender);
    
    const contentDiv = document.createElement("div");
    contentDiv.classList.add("message-content");
    contentDiv.innerText = message;
    
    messageDiv.appendChild(contentDiv);
    chatLog.appendChild(messageDiv);
    chatLog.scrollTop = chatLog.scrollHeight;
  }
  
  // Adds a conversation snippet to the sidebar
  function addConversationToSidebar(convoId, convo) {
    let snippet = convo.messages.find(msg => msg.role === "user")?.content || "Empty conversation";
    if (snippet.length > 30) {
      snippet = snippet.slice(0, 30) + "...";
    }
    const conversationDiv = document.createElement("div");
    conversationDiv.classList.add("conversation-item");
    conversationDiv.dataset.convoId = convoId;
    conversationDiv.innerText = `Model: ${convo.model} - ${snippet}`;
    conversationDiv.addEventListener("click", () => loadConversation(convoId));
    conversationsList.prepend(conversationDiv);
  }
  
  // Updates an existing conversation snippet in the sidebar
  function updateConversationInSidebar(convoId, convo) {
    const convDiv = document.querySelector(`.conversation-item[data-convo-id='${convoId}']`);
    if (convDiv) {
      let snippet = convo.messages.find(msg => msg.role === "user")?.content || "Empty conversation";
      if (snippet.length > 30) {
        snippet = snippet.slice(0, 30) + "...";
      }
      convDiv.innerText = `Model: ${convo.model} - ${snippet}`;
    }
  }
  
  // Loads an entire stored conversation into the main chat window
  function loadConversation(convoId) {
    if (savedConversations.hasOwnProperty(convoId)) {
      const convo = savedConversations[convoId];
      activeModel = convo.model;
      activeConversation = convo.messages.slice();
      activeConversationId = convoId;
      isResumed = true;
      isConversationModified = false;
      chatLog.innerHTML = "";
      activeConversation.forEach(msg => {
        appendMessage(msg.role, msg.content);
      });
    }
  }
});