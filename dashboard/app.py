"""Streamlit dashboard for SG Restaurant AEO.

Interactive exploration of LLM restaurant recommendation data.
Launch with: streamlit run dashboard/app.py

This dashboard will be fully implemented in Phase 4.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="SG Restaurant AEO",
    page_icon="🍜",
    layout="wide",
)

st.title("What Does AI Think About Singapore Restaurants?")
st.markdown("*A systematic study of LLM-mediated restaurant discovery*")

st.info("Dashboard coming in Phase 4. Run the query sweep and parser first.")
