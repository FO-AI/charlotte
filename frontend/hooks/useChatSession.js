import { useState, useEffect } from 'react';
import { useAuth } from '../lib/auth/auth-context-msal';
import { APIClient } from '../lib/api-client';
import { azureCosmosClient } from '../lib/azure-cosmos-client';

const DEFAULT_MODE = "EDI";

const useChatSession = () => {
    const [conversationId, setConversationId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [chatStarted, setChatStarted] = useState(false);
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const [isMobile, setIsMobile] = useState(false);
    const [mode, setMode] = useState(DEFAULT_MODE);
    const [modeLocked, setModeLocked] = useState(false);
    const [conversationModes, setConversationModes] = useState({});
    const { getAuthHeaders, user } = useAuth();

    const apiClient = new APIClient(getAuthHeaders);

    useEffect(() => {
        if (getAuthHeaders) {
            azureCosmosClient.setAuthHeaders(getAuthHeaders);
        }
    }, [getAuthHeaders]);

    // Check for mobile on mount and resize
    useEffect(() => {
        const checkMobile = () => {
            const mobile = window.innerWidth < 1024;
            setIsMobile(mobile);
            // Auto-collapse sidebar on mobile
            if (mobile) {
                setSidebarCollapsed(true);
            }
        };

        checkMobile();
        window.addEventListener('resize', checkMobile);
        return () => window.removeEventListener('resize', checkMobile);
    }, []);
    const generateConversationTitle = (message) => {
        // Generate a title from the first message (limit to 50 characters)
        return message.length > 50 ? message.substring(0, 50) + "..." : message;
      };


      const handleDeleteConversation = (id) => {
        setConversationModes((prev) => {
          if (!(id in prev)) return prev;
          const { [id]: _removed, ...rest } = prev;
          return rest;
        });
        if (conversationId === id) {
          handleNewChat();
        }
      };

      const handleRenameConversation = async (id, newTitle) => {
        try {
          await azureCosmosClient.renameSession(id, newTitle);
          // Update conversation modes if needed
          // The sidebar will handle its own state update
        } catch (error) {
          console.error("Error renaming conversation:", error);
          throw error;
        }
      };
      const determineModeFromMessages = (chatMessages = []) => {
        if (!Array.isArray(chatMessages) || chatMessages.length === 0) {
          return DEFAULT_MODE;
        }
    
        for (let idx = chatMessages.length - 1; idx >= 0; idx--) {
          const message = chatMessages[idx];
          if (message?.role !== "assistant") continue;
    
          if (message?.queryType === "edi_search" || (Array.isArray(message?.transactions) && message.transactions.length > 0)) {
            return "EDI";
          }
    
          if (message?.queryType === "general_ai") {
            return "PROCEDURE";
          }
        }
    
        return DEFAULT_MODE;
      };





      const handleNewChat = (newSession = null) => {
        const newConversationId = newSession?.id || null;
        setMessages([]);
        setConversationId(newConversationId);
        setChatStarted(false);
        setInput("");
        if (newConversationId && conversationModes[newConversationId]) {
          setMode(conversationModes[newConversationId]);
          setModeLocked(Boolean(newSession?.messages?.length));
        } else {
          setMode(DEFAULT_MODE);
          setModeLocked(false);
        }
    
        // Auto-collapse sidebar on mobile after creating new chat
        if (isMobile) {
          setSidebarCollapsed(true);
        }
      };
      const handleSelectConversation = async (id) => {
        try {
          // Load conversation from Azure Cosmos DB
          const session = await azureCosmosClient.getSession(id);
          if (session) {
            const sessionMessages = session.messages || [];
            setConversationId(id);
            setMessages(sessionMessages);
            const hasMessages = sessionMessages.length > 0;
            setChatStarted(hasMessages);
            const derivedMode = conversationModes[id] || determineModeFromMessages(sessionMessages);
            setConversationModes((prev) => ({
              ...prev,
              [id]: derivedMode,
            }));
            setMode(derivedMode);
            setModeLocked(hasMessages);
    
            // Auto-collapse sidebar on mobile after selection
            if (isMobile) {
              setSidebarCollapsed(true);
            }
          }
        } catch (error) {
          console.error("Error loading conversation:", error);
          // Fallback to new chat if loading fails
          handleNewChat();
          setConversationId(id);
        }
      };


    const handleSubmit = async (e) => {
        e.preventDefault();

        if (!input.trim() || isSubmitting) return;

        const isFirstMessage = !chatStarted;
        const userMessage = input.trim();
        setInput("");

        // Mark chat as started on first message
        if (isFirstMessage) {
        setChatStarted(true);
        setModeLocked(true);
        }

        // Add user message to chat
        setMessages((prev) => [
        ...prev,
        { role: "user", content: userMessage },
        { role: "assistant", content: "", isLoading: true },
        ]);

        setIsSubmitting(true);

        try {
        const data = await apiClient.sendChatQuery({
            query: userMessage,
            conversation_id: conversationId,
            mode: mode,
            messages: messages.map(msg => ({
            role: msg.role,
            content: msg.content
            }))
        });

        // Set conversation ID if this is the first message
        if (!conversationId && data.conversation_id) {
            const newConversationId = data.conversation_id;
            setConversationId(newConversationId);
        }

        // Update assistant message with response
        const updatedMessages = messages.concat([
            { role: "user", content: userMessage },
            {
            role: "assistant",
            content: data.response || data.answer,
            sources: data.sources,
            transactions: data.data,
            queryType: data.type,
            transactionsFound: data.transactions_found,
            }
        ]);

        setMessages((prev) =>
            prev.map((msg, i) => {
            if (i === prev.length - 1 && msg.isLoading) {
                return {
                role: "assistant",
                content: data.response || data.answer,
                sources: data.sources,
                transactions: data.data,
                queryType: data.type,
                transactionsFound: data.transactions_found,
                isLoading: false,
                };
            }
            return msg;
            })
        );

        // Persist messages to Azure Cosmos DB
        try {
            const currentConversationId = conversationId || data.conversation_id;
            if (currentConversationId) {
            setConversationModes((prev) => ({
                ...prev,
                [currentConversationId]: mode,
            }));
            }
            if (currentConversationId && user?.email) {
            if (!conversationId) {
                // Create new session for first message
                await azureCosmosClient.createNewSession(
                currentConversationId,
                user.email,
                generateConversationTitle(userMessage)
                );
            }

            await azureCosmosClient.updateSession(
                currentConversationId,
                user.email,
                updatedMessages
            );
            }
        } catch (dbError) {
            console.error("Error persisting messages to database:", dbError);
            // Don't block the UI if database save fails
        }
        } catch (error) {
        console.error("Error querying API:", error);

        // Update loading message with error
        setMessages((prev) =>
            prev.map((msg, i) => {
            if (i === prev.length - 1 && msg.isLoading) {
                return {
                role: "assistant",
                content: "I'm sorry, I encountered an error while processing your request. Please try again later.",
                isLoading: false,
                };
            }
            return msg;
            })
        );
        } finally {
        setIsSubmitting(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit(e);
        }
    };

    return {
        conversationId,
        messages,
        input,
        isSubmitting,
        chatStarted,
        sidebarCollapsed,
        isMobile,
        mode,
        modeLocked,
        conversationModes,
        user,
        getAuthHeaders,
        // Setters
        setInput,
        setMessages,
        setConversationId,
        setChatStarted,
        setMode,
        setModeLocked,
        setSidebarCollapsed,
        setIsMobile,
        // Handlers
        handleDeleteConversation,
        handleRenameConversation,
        handleSelectConversation,
        handleNewChat,
        handleSubmit,
        handleKeyDown,
    };
}

export default useChatSession;