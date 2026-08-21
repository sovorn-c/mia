"""Modern Carrot-Orange Design System and Textual CSS styles for Mia Herd."""

MIA_THEME_CSS = """
Screen {
    background: #0D0F12;
    color: #F3F4F6;
}

/* --- Header --- */
HerdHeader {
    dock: top;
    height: 3;
    background: #16191E;
    color: #F3F4F6;
    border-bottom: solid #2B303B;
    padding: 0 1;
}

#header-title {
    color: #FF7A00;
    text-style: bold;
}

#header-status {
    color: #9CA3AF;
}

/* --- Main Layout --- */
#main-layout {
    layout: horizontal;
    height: 1fr;
    background: #0D0F12;
}

/* --- Sidebar --- */
HerdSidebar {
    width: 32;
    background: #12151A;
    border-right: solid #2B303B;
    padding: 1;
}

.sidebar-title {
    color: #9CA3AF;
    text-style: bold;
    margin-bottom: 1;
}

AgentListItem {
    height: auto;
    padding: 1;
    margin-bottom: 1;
    background: #16191E;
    border: solid #2B303B;
}

AgentListItem:hover {
    background: #20242C;
    border: solid #FF7A00;
}

AgentListItem.-active {
    background: #20242C;
    border-left: thick #FF7A00;
    border-top: solid #2B303B;
    border-right: solid #2B303B;
    border-bottom: solid #2B303B;
}

/* --- Main Transcript Pane --- */
AgentPaneContainer {
    width: 1fr;
    height: 1fr;
    background: #0D0F12;
    padding: 1;
}

#transcript-scroll {
    height: 1fr;
    scrollbar-color: #FF7A00 #16191E;
}

/* --- Card Widgets --- */
UserMessageCard {
    background: #16191E;
    border-left: thick #FF7A00;
    border-top: solid #2B303B;
    border-right: solid #2B303B;
    border-bottom: solid #2B303B;
    padding: 1;
    margin-bottom: 1;
}

AssistantMessageCard {
    background: #16191E;
    border: solid #2B303B;
    padding: 1;
    margin-bottom: 1;
}

ThoughtDrawer {
    background: #12151A;
    border: solid #2B303B;
    padding: 0 1;
    margin-bottom: 1;
}

.thought-header {
    color: #FF7A00;
    text-style: italic;
}

.thought-body {
    color: #9CA3AF;
    text-style: italic;
    padding: 1 0;
}

ToolCallCard {
    background: #16191E;
    border: solid #2B303B;
    padding: 1;
    margin-bottom: 1;
}

.tool-header {
    color: #38BDF8;
    text-style: bold;
}

.tool-success {
    color: #10B981;
}

.tool-error {
    color: #EF4444;
}

/* --- Input Area --- */
#input-container {
    dock: bottom;
    height: auto;
    max-height: 8;
    background: #16191E;
    border-top: solid #2B303B;
    padding: 0 1;
}

#input-container:focus-within {
    border-top: solid #FF7A00;
}

PromptInput {
    background: #16191E;
    border: none;
    color: #F3F4F6;
    height: auto;
    min-height: 3;
}

/* --- Footer --- */
HerdFooter {
    dock: bottom;
    height: 1;
    background: #0D0F12;
    color: #9CA3AF;
    padding: 0 1;
}
"""
