from __future__ import annotations

import pathlib

import streamlit as st


def inject_fonts() -> None:
    """Inject a modern, Apple-like font stack.

    We use Inter as a high-quality web font, while keeping a system fallback that
    looks native on Apple platforms (SF Pro via system font).
    """
    st.markdown(
        """
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
          html, body, [data-testid="stAppViewContainer"] {
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_ui() -> None:
    """Apply the Liquid Glass CSS and safe Streamlit baseline tweaks."""
    css_path = pathlib.Path(__file__).with_name("liquid_glass.css")
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

    st.markdown(
        """
        <style>
          .block-container { padding-top: 1.1rem; padding-bottom: 2.2rem; }
          [data-testid="stMetricValue"] { font-weight: 800; letter-spacing: -0.02em; }
          [data-testid="stMetricLabel"] { opacity: 0.92; }
          [data-testid="stToolbar"] { visibility: visible; height: auto; }
          /* Smoothness */
          * { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Modern motion: reveal key containers when they enter the viewport.
    # (Pure front-end; no external dependencies.)
    st.markdown(
        """
        <script>
        (function(){
          // Inject background layers once
          // Parallax (GPU-friendly): update a CSS var based on scroll position
          let ticking = false;
          const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
          const onScroll = () => {
            if(ticking) return;
            ticking = true;
            window.requestAnimationFrame(() => {
              const y = window.scrollY || document.documentElement.scrollTop || 0;
              // subtle parallax; capped so it never jitters
              const py = clamp(y * -0.03, -28, 0);
              document.documentElement.style.setProperty('--lg-parallax-y', py + 'px');
              ticking = false;
            });
          };
          window.addEventListener('scroll', onScroll, {passive:true});
          onScroll();


          if(!document.querySelector('.lg-bg-mesh')){
            const mesh = document.createElement('div'); mesh.className='lg-bg-mesh';
            const blobs = document.createElement('div'); blobs.className='lg-bg-blobs';
            const parts = document.createElement('div'); parts.className='lg-bg-particles';
            document.body.appendChild(mesh);
            document.body.appendChild(blobs);
            document.body.appendChild(parts);
          }

          const SELECTORS = [
            'div[data-testid="stMetric"]',
            'div[data-testid="stVegaLiteChart"]',
            'div[data-testid="stAltairChart"]',
            'div[data-testid="stPlotlyChart"]',
            'div[data-testid="stDataFrame"]',
            '.lg-glass'
          ];

          const els = [];
          SELECTORS.forEach(sel => document.querySelectorAll(sel).forEach(el => els.push(el)));

          // Mark for reveal
          els.forEach(el => el.classList.add('lg-reveal'));

          // Reveal on enter
          const io = new IntersectionObserver((entries)=>{
            entries.forEach(e=>{
              if(e.isIntersecting){
                e.target.style.willChange = 'transform, opacity, filter';
                // restart animation by forcing reflow when needed
                e.target.classList.remove('lg-reveal');
                void e.target.offsetWidth;
                e.target.classList.add('lg-reveal');
                io.unobserve(e.target);
              }
            });
          }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

          els.forEach(el => io.observe(el));
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )