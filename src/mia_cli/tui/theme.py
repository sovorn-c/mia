"""Modern Carrot-Orange Design System and sleek OpenCode/Pi-style Textual CSS."""

MIA_THEME_CSS = """
Screen {
    background: #0D0F12;
    color: #F3F4F6;
}

/* --- Top Header Bar --- */
MiaHeader {
    dock: top;
    height: 1;
    background: #13161D;
    color: #9CA3AF;
    padding: 0 1;
}

#header-content {
    width: 100%;
    height: 100%;
}

/* --- Main Layout --- */
#main-layout {
    layout: horizontal;
    height: 1fr;
    background: #0D0F12;
}

/* --- Sidebar --- */
AgentSidebar {
    width: 30;
    background: #101217;
    border-right: solid #1C202A;
    padding: 0 1;
}

.sidebar-title {
    color: #6B7280;
    text-style: bold;
    margin: 1 0;
}

AgentListItem {
    height: auto;
    padding: 1;
    margin-bottom: 1;
    background: transparent;
    border: none;
}

AgentListItem:hover {
    background: #161A22;
}

AgentListItem.-active {
    background: #1A1E28;
    border-left: thick #FF7A00;
}

.agent-item-header {
    text-style: bold;
}

.agent-item-details {
    color: #6B7280;
    text-style: dim;
}

/* --- Main Transcript Stream (Pi-style clean minimal flow) --- */
AgentPaneContainer {
    width: 1fr;
    height: 1fr;
    background: #0D0F12;
    padding: 0 1;
}

.pane-header-title {
    height: 1;
    color: #6B7280;
    margin: 0 0 1 0;
}

AgentTranscriptView {
    height: 1fr;
    scrollbar-color: #FF7A00 #13161D;
    scrollbar-size: 1 1;
}

/* --- Message Bubbles & Cards --- */
UserMessageCard {
    background: #141720;
    border-left: thick #FF7A00;
    padding: 1;
    margin: 1 0;
}

.user-msg-header {
    color: #FF7A00;
    text-style: bold;
    margin-bottom: 1;
}

.user-msg-body {
    color: #F3F4F6;
}

AssistantMessageCard {
    background: transparent;
    border: none;
    padding: 0 1;
    margin: 1 0;
}

.assistant-msg-body {
    color: #F3F4F6;
}

ThoughtDrawer {
    background: #10131A;
    border-left: solid #FF7A00;
    padding: 0 1;
    margin: 1 0;
}

.thought-header {
    color: #FF7A00;
    text-style: bold italic;
    padding: 1 0;
}

.thought-body {
    color: #9CA3AF;
    text-style: italic;
    padding: 0 0 1 0;
}

ToolCallCard {
    background: #12151D;
    border-left: solid #38BDF8;
    padding: 0 1;
    margin: 1 0;
}

.tool-header {
    color: #38BDF8;
    text-style: bold;
    padding: 1 0;
}

.tool-body {
    padding: 0 0 1 0;
    color: #9CA3AF;
}

/* --- Bottom Prompt Editor --- */
MiaPromptEditor {
    dock: bottom;
    height: auto;
    min-height: 4;
    max-height: 10;
    background: #141720;
    border-top: solid #1C202A;
    padding: 0 1;
}

MiaPromptEditor:focus-within {
    border-top: solid #FF7A00;
}

#editor-row {
    height: auto;
    min-height: 3;
}

.editor-prefix {
    width: 5;
    color: #FF7A00;
    text-style: bold;
    padding-top: 0;
}

PromptTextArea {
    height: auto;
    min-height: 2;
    max-height: 8;
    background: #141720;
    border: none;
    color: #F3F4F6;
    padding: 0;
}

PromptTextArea:focus {
    border: none;
}

.editor-hint {
    height: 1;
    color: #6B7280;
    text-style: dim;
    margin-top: 0;
}

/* --- Footer --- */
MiaFooter {
    dock: bottom;
    height: 1;
    background: #0D0F12;
    color: #6B7280;
    padding: 0 1;
}
"""
