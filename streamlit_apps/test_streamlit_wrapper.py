
import sys
import asyncio
from asyncio import windows_events

# CRITICAL: Force SelectorEventLoopPolicy BEFORE any asyncio/tornado usage
windows_events.set_event_loop_policy(windows_events.WindowsSelectorEventLoopPolicy())

# Now import and run streamlit
import streamlit.cli
streamlit.cli.main()
