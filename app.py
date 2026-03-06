import hashlib
import math
import random
import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import urllib.parse
import asyncio
import pandas as pd
import pydeck as pdk
import time
from openai import OpenAI
from datetime import datetime, timedelta
from streamlit_geolocation import streamlit_geolocation
from supabase import create_client, Client
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_not_exception_type

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
TIER_1_NAMES = ["The Sure Thing", "The Crowd Pleaser", "The Local Favorite", "The Classic", "The Reliable"]
TIER_2_NAMES = ["The Fresh Take", "The Curveball", "The Surprise", "The Interesting Pick", "The Plot Twist"]
TIER_3_NAMES = ["The Hidden Gem", "The Wild Card", "The Adventure", "The Deep Cut", "The Discovery"]

NON_TRADITIONAL_INDOOR = [
    "escape room", "axe throwing", "pottery studio", "art class",
    "cooking class", "improv comedy club", "karaoke bar",
    "bowling alley", "arcade bar", "rage room", "paint and sip",
    "maker space", "climbing gym", "trampoline park",
    "virtual reality arcade", "board game cafe", "glass blowing studio",
    "ceramics studio", "dance class", "murder mystery dinner",
]

NON_TRADITIONAL_OUTDOOR = [
    "hiking trail", "bike trail", "kayak rental", "canoe rental",
    "rock climbing", "disc golf", "botanical garden", "arboretum",
    "scenic overlook", "waterfall", "swimming hole", "farm",
    "vineyard tour", "orchard", "zip line", "paddleboard rental",
    "outdoor climbing wall", "community garden", "nature preserve",
]

CACHE_VERSION = "v2"

POINTS = {
    'first_save':       10,
    'save':              1,
    'going_top3':        3,
    'going_wild':        5,
    'rate':              2,
    'rate_perfect':      3,   # additional pts for 5-star rating
    'invite_sent':      10,
    'friend_activated': 15,
    'wild_idea':         3,
}

BADGES = [
    # Explorer
    {'id': 'first_step',  'name': 'First Step',         'emoji': '🧭', 'pts': 5,
     'desc': 'Save your first spot',
     'check': lambda s: s['total_saves'] >= 1},
    {'id': 'committed',   'name': 'Committed',           'emoji': '🎯', 'pts': 10,
     'desc': 'Choose your first outing',
     'check': lambda s: s['total_chosen'] >= 1},
    {'id': 'keep_going',  'name': 'Keep It Going',       'emoji': '🔄', 'pts': 15,
     'desc': 'Choose 5 outings',
     'check': lambda s: s['total_chosen'] >= 5},
    {'id': 'trailblazer', 'name': 'Trailblazer',         'emoji': '🥾', 'pts': 25,
     'desc': 'Choose 10 outings',
     'check': lambda s: s['total_chosen'] >= 10},
    {'id': 'wild_legend', 'name': 'Wild Legend',         'emoji': '👑', 'pts': 100,
     'desc': 'Choose 50 outings',
     'check': lambda s: s['total_chosen'] >= 50},
    # GET WILD
    {'id': 'first_wild',  'name': 'First Wild',          'emoji': '⚡', 'pts': 10,
     'desc': 'First GET WILD outing',
     'check': lambda s: s['wild_chosen'] >= 1},
    {'id': 'wild_at_heart','name': 'Wild at Heart',      'emoji': '🎲', 'pts': 20,
     'desc': '5 GET WILD outings',
     'check': lambda s: s['wild_chosen'] >= 5},
    {'id': 'untamed',     'name': 'Untamed',             'emoji': '🌪️', 'pts': 50,
     'desc': '25 GET WILD outings',
     'check': lambda s: s['wild_chosen'] >= 25},
    {'id': 'wild_thinker','name': 'Wild Thinker',        'emoji': '💡', 'pts': 15,
     'desc': 'Complete 3 Wild Ideas',
     'check': lambda s: s['wild_idea_chosen'] >= 3},
    # Taste
    {'id': 'foodie',      'name': 'Foodie',              'emoji': '🍽️', 'pts': 10,
     'desc': 'Rate 5 dining spots 4+ stars',
     'check': lambda s: s['rated_dining_4plus'] >= 5},
    {'id': 'sommelier',   'name': 'Sommelier',           'emoji': '🍷', 'pts': 10,
     'desc': 'Save 5 wine bars or wineries',
     'check': lambda s: s['wine_saves'] >= 5},
    {'id': 'hop_head',    'name': 'Hop Head',            'emoji': '🍺', 'pts': 10,
     'desc': 'Save 5 breweries',
     'check': lambda s: s['brewery_saves'] >= 5},
    {'id': 'coffee_snob', 'name': 'Coffee Snob',         'emoji': '☕', 'pts': 5,
     'desc': 'Save 3 coffee shops',
     'check': lambda s: s['coffee_saves'] >= 3},
    {'id': 'splurge_worthy','name': 'Splurge Worthy',   'emoji': '✨', 'pts': 15,
     'desc': 'Choose 3 Splurge outings',
     'check': lambda s: s['splurge_chosen'] >= 3},
    # Vibe
    {'id': 'romantic',    'name': 'Romantic',            'emoji': '💑', 'pts': 15,
     'desc': '5 Date outings chosen',
     'check': lambda s: s['date_chosen'] >= 5},
    {'id': 'family_first','name': 'Family First',        'emoji': '👨‍👩‍👧', 'pts': 15,
     'desc': '5 Family outings chosen',
     'check': lambda s: s['family_chosen'] >= 5},
    {'id': 'social_butterfly','name': 'Social Butterfly','emoji': '👯', 'pts': 15,
     'desc': '5 Friends outings chosen',
     'check': lambda s: s['friends_chosen'] >= 5},
    {'id': 'outdoorsy',   'name': 'Outdoorsy',           'emoji': '🌲', 'pts': 15,
     'desc': '5 outdoor outings chosen',
     'check': lambda s: s['outdoor_chosen'] >= 5},
    {'id': 'gem_hunter',  'name': 'Gem Hunter',          'emoji': '💎', 'pts': 20,
     'desc': 'Save 5 Hidden Gem tier spots',
     'check': lambda s: s['hidden_gem_saves'] >= 5},
    {'id': 'culture_vulture','name': 'Culture Vulture',  'emoji': '🎭', 'pts': 10,
     'desc': 'Save 3 museums, galleries, or theaters',
     'check': lambda s: s['culture_saves'] >= 3},
    {'id': 'live_wire',   'name': 'Live Wire',           'emoji': '🎵', 'pts': 15,
     'desc': 'Attend 3 live events',
     'check': lambda s: s['event_chosen'] >= 3},
    {'id': 'freeloader',  'name': 'Freeloader',          'emoji': '🆓', 'pts': 10,
     'desc': 'Complete 5 Free budget outings',
     'check': lambda s: s['free_chosen'] >= 5},
    # Social
    {'id': 'evangelist',  'name': 'Evangelist',          'emoji': '📣', 'pts': 5,
     'desc': 'Invite your first friend',
     'check': lambda s: s['referral_count'] >= 1},
    {'id': 'community',   'name': 'Community',           'emoji': '🌱', 'pts': 20,
     'desc': '3 friends sign up via your link',
     'check': lambda s: s['referral_count'] >= 3},
    {'id': 'wildfire',    'name': 'Wildfire',            'emoji': '🔥', 'pts': 75,
     'desc': '10 friends sign up via your link',
     'check': lambda s: s['referral_count'] >= 10},
]

GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
TICKETMASTER_API_KEY = st.secrets["TICKETMASTER_API_KEY"]
OPENWEATHER_API_KEY = st.secrets["OPENWEATHER_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
try:
    ALLTRAILS_API_KEY = st.secrets["ALLTRAILS_API_KEY"]
except:
    ALLTRAILS_API_KEY = None

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_supabase()

# ==========================================
# 2. CUSTOM CSS & STYLING
# ==========================================
st.set_page_config(page_title="Get Wild", page_icon="🌿", layout="centered")

custom_css = """
<style>
    /* HERO */
    .hero-header { text-align: center; padding: 2rem 0 1rem 0; }
    .hero-title { color: #2e7d32; font-family: 'Helvetica Neue', sans-serif; font-size: 3.5rem; font-weight: 800; letter-spacing: -1px; text-transform: uppercase; margin-bottom: 0; line-height: 1.1; }
    .hero-subtitle { color: #558b2f; font-size: 1.2rem; font-weight: 400; letter-spacing: 1px; margin-top: 10px; }

    /* CARD */
    .wc-shell { overflow: hidden; animation: fadeSlideUp 0.5s ease-out forwards; }

    /* Card inner content */
    .wc-img-wrap { position: relative; width: 100%; height: 200px; overflow: hidden; }
    .wc-img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .wc-tier { position: absolute; bottom: 10px; left: 12px; background: rgba(0,0,0,0.75); color: #fff; font-size: 0.875rem; font-weight: 600; letter-spacing: 0.5px; padding: 5px 10px; border-radius: 20px; text-transform: uppercase; }

    .wc-body { padding: 16px; }
    .wc-name { font-size: 20px; font-weight: 700; color: #1a1a1a; margin: 0 0 5px 0; line-height: 1.3; }
    .wc-meta { font-size: 0.78rem; color: #888; margin-bottom: 4px; font-weight: 500; }
    .wc-vibe-row { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 6px; }
    .wc-vibe-pill { font-size: 12px; color: #444; background: #f0f0f0; border-radius: 12px; padding: 3px 10px; font-weight: 500; }
    @media (prefers-color-scheme: dark) { .wc-vibe-pill { background: #2a2a2a; color: #ccc; } }
    .wc-address { font-size: 12px; color: #aaa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 12px; }
    .wc-hr { border: none; border-top: 1px solid #f0f0f0; margin: 12px 0; }
    .wc-pitch { font-size: 14px; line-height: 1.6; color: #444; margin: 0 0 8px 0; }
    .wc-tags { margin: 0 0 2px 0; }
    .wc-tag { display: inline-block; background: #e8f5e9; color: #2e7d32; padding: 3px 10px; border-radius: 12px; font-size: 0.73rem; font-weight: 600; margin: 2px 4px 2px 0; border: 1px solid #c8e6c9; }

    .wc-utility { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; margin-bottom: 12px; }
    .wc-util-link { color: #aaa; font-size: 0.78rem; text-decoration: none; font-weight: 500; transition: color 0.15s; }
    .wc-util-link:hover { color: #555; text-decoration: underline; }
    .wc-util-sep { color: #ddd; padding: 0 4px; font-size: 0.78rem; }

    /* Dark mode */
    @media (prefers-color-scheme: dark) {
        .stTextInput > label, .stSelectbox > label, .stRadio > label,
        .stCheckbox > label, .stTextArea > label, .stMultiSelect > label,
        .stSlider > label, .stNumberInput > label { color: #f0f0f0 !important; }
        .wc-name { color: #f0f0f0 !important; }
        .wc-meta, .wc-address { color: #999 !important; }
        .wc-pitch { color: #ccc !important; }
        .wc-hr { border-color: #333 !important; }
        .wc-util-link { color: #666 !important; }
        .wc-util-link:hover { color: #999 !important; }
        .wc-tag { background: #1a3320 !important; border-color: #2a5230 !important; }
    }

    @keyframes fadeSlideUp { from {opacity: 0; transform: translateY(20px);} to { opacity: 1; transform: translateY(0); } }
    @keyframes wildGlow {
        0%, 100% { box-shadow: 0 0 20px rgba(45,106,79,0.4), 0 0 40px rgba(45,106,79,0.2); }
        50%       { box-shadow: 0 0 30px rgba(45,106,79,0.6), 0 0 60px rgba(45,106,79,0.3); }
    }

    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    header[data-testid="stHeader"] {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
    [data-testid="stDecoration"] {visibility: hidden;}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

def scroll_to_top():
    components.html(
        """
        <script>
            var body = window.parent.document.querySelector(".main");
            if (body) { body.scrollTop = 0; }
        </script>
        """,
        height=0
    )

# ==========================================
# 3. SESSION STATE & DATABASE HELPERS
# ==========================================
if 'user' not in st.session_state: st.session_state.user = None
if 'current_results' not in st.session_state: st.session_state.current_results = None 
if 'current_mode' not in st.session_state: st.session_state.current_mode = None
if 'session_seen_spots' not in st.session_state: st.session_state.session_seen_spots = []
if 'search_active' not in st.session_state: st.session_state.search_active = False
if 'trigger_fetch' not in st.session_state: st.session_state.trigger_fetch = False
if 'saved_spots_dirty' not in st.session_state: st.session_state.saved_spots_dirty = False
if 'fetch_timed_out' not in st.session_state: st.session_state.fetch_timed_out = False
if 'skip_cache' not in st.session_state: st.session_state.skip_cache = False
if 'show_onboarding' not in st.session_state: st.session_state.show_onboarding = False
if 'wild_idea_dismissed' not in st.session_state: st.session_state.wild_idea_dismissed = False
if 'wild_idea_expanded' not in st.session_state: st.session_state.wild_idea_expanded = False
if 'show_welcome_bonus' not in st.session_state: st.session_state.show_welcome_bonus = False
if 'referral_code' not in st.session_state:
    st.session_state.referral_code = st.query_params.get("ref", "")

# Persistent memory state variables
if 'mem_loc' not in st.session_state: st.session_state.mem_loc = ""
if 'mem_day' not in st.session_state: st.session_state.mem_day = "☀️ Today"
if 'mem_time' not in st.session_state: st.session_state.mem_time = "🌙 Night"
if 'mem_group' not in st.session_state: st.session_state.mem_group = "Date"
if 'mem_vibe' not in st.session_state: st.session_state.mem_vibe = "Doesn't Matter"
if 'mem_food' not in st.session_state: st.session_state.mem_food = "Full Meal"
if 'mem_dist' not in st.session_state: st.session_state.mem_dist = 5
if 'mem_spend' not in st.session_state: st.session_state.mem_spend = "💰 Moderate"
# Migrate old 4-option spend values to new 3-option format
_spend_migrate = {"$ Affordable": "💰 Moderate", "$ Moderate": "💰 Moderate", "$$ Splurge": "✨ Splurge"}
if st.session_state.mem_spend in _spend_migrate:
    st.session_state.mem_spend = _spend_migrate[st.session_state.mem_spend]
if 'mem_spec' not in st.session_state: st.session_state.mem_spec = ""
if 'mem_gps_active' not in st.session_state: st.session_state.mem_gps_active = False
if 'mem_geo_data' not in st.session_state: st.session_state.mem_geo_data = None

def get_profile(user_id):
    try:
        res = supabase.table('user_profiles').select('*').eq('id', user_id).execute()
        return res.data[0] if res.data else None
    except: return None

def get_excluded_spots(user_id):
    try:
        res = supabase.table('saved_spots').select('spot_name').eq('user_id', user_id).execute()
        return [spot['spot_name'] for spot in res.data] if res.data else []
    except: return []

def get_favorite_spots(user_id):
    try:
        # Pull spots rated 4 or 5 stars to train the AI
        res = supabase.table('saved_spots').select('spot_name, category').eq('user_id', user_id).gte('rating', 4).execute()
        return [f"{spot['spot_name']} ({spot['category']})" for spot in res.data] if res.data else []
    except: return []

def generate_referral_code(user_id):
    """Returns the user's referral code, generating and saving one if needed."""
    try:
        res = supabase.table('user_profiles').select('referral_code').eq('id', user_id).execute()
        if res.data and res.data[0].get('referral_code'):
            return res.data[0]['referral_code']
        import hashlib
        code = hashlib.md5(f"{user_id}getwild".encode()).hexdigest()[:8].upper()
        supabase.table('user_profiles').upsert({'id': user_id, 'referral_code': code}).execute()
        return code
    except:
        return None

def get_user_preference_scores(user_id):
    """Returns learned taste profile from saved/rated spots."""
    _TASTE_KEYWORDS = [
        "wine", "brewery", "bar", "coffee", "museum", "outdoor", "music",
        "comedy", "sports", "restaurant", "jazz", "cocktail", "theater", "brunch",
    ]
    try:
        res = supabase.table('saved_spots').select('spot_name, category, rating').eq('user_id', user_id).execute()
        spots = res.data or []
        if not spots:
            return {}

        # Category scoring: count * avg_rating for rated>=4 spots
        from collections import defaultdict
        cat_ratings = defaultdict(list)
        kw_counts = defaultdict(int)
        avoid_kw_counts = defaultdict(int)

        for spot in spots:
            rating = spot.get('rating') or 0
            cat = (spot.get('category') or '').strip()
            name = (spot.get('spot_name') or '').lower()
            cat_lower = cat.lower()
            combined = name + ' ' + cat_lower

            if rating >= 4:
                if cat:
                    cat_ratings[cat].append(rating)
                for kw in _TASTE_KEYWORDS:
                    if kw in combined:
                        kw_counts[kw] += 1
            elif rating == 1:
                for kw in _TASTE_KEYWORDS:
                    if kw in combined:
                        avoid_kw_counts[kw] += 1

        # Score = count * avg_rating per category
        cat_scores = {
            cat: len(ratings) * (sum(ratings) / len(ratings))
            for cat, ratings in cat_ratings.items()
        }
        top_categories = sorted(cat_scores, key=cat_scores.get, reverse=True)[:3]
        top_keywords = sorted(kw_counts, key=kw_counts.get, reverse=True)[:5]
        top_keywords = [kw for kw in top_keywords if kw_counts[kw] >= 2]  # min 2 mentions
        avoid_keywords = [kw for kw in avoid_kw_counts if avoid_kw_counts[kw] >= 2]

        return {
            "top_categories": top_categories,
            "top_keywords": top_keywords,
            "avoid_keywords": avoid_keywords,
            "rated_count": len([s for s in spots if (s.get('rating') or 0) >= 4]),
        }
    except:
        return {}

def save_spot_to_db(user_id, name, address, category, rating=None, notes="",
                    mode="", group_type="", setting="", spend="", tier_name=""):
    """Save a spot. Returns pre-save row count (0 = first save ever). Returns -1 on error."""
    try:
        pre_count = 0
        try:
            res = supabase.table('saved_spots').select('id', count='exact').eq('user_id', user_id).execute()
            pre_count = res.count or 0
        except:
            pass

        supabase.table('saved_spots').insert({
            'user_id':    user_id,
            'spot_name':  name,
            'address':    address,
            'category':   category,
            'rating':     rating,
            'user_notes': notes,
            'saved_at':   datetime.utcnow().isoformat(),
            'mode':       mode or '',
            'group_type': group_type or '',
            'setting':    setting or '',
            'spend':      spend or '',
            'tier_name':  tier_name or '',
        }).execute()

        if rating != 1:
            prof = get_profile(user_id)
            new_tally = (prof.get('wild_tally') or 0) + 1
            supabase.table('user_profiles').update({'wild_tally': new_tally}).eq('id', user_id).execute()
            st.toast(f"✅ Saved! Your Get Wild Tally is now {new_tally} 🏆")
        else:
            st.toast("🚫 Blacklisted. We won't recommend this again.")
        return pre_count
    except Exception as e:
        st.error("Database error.")
        return -1

def generate_cache_key(filters_dict, location_name, target_date_str, mode):
    raw = json.dumps(filters_dict, sort_keys=True) + location_name + target_date_str + mode + CACHE_VERSION
    return hashlib.md5(raw.encode()).hexdigest()

def delete_spot_from_db(spot_id):
    try:
        supabase.table('saved_spots').delete().eq('id', spot_id).execute()
        st.toast("🗑️ Spot permanently deleted.")
        return True
    except Exception as e:
        st.error(f"Database error while deleting: {e}")
        return False

def get_user_points(user_id):
    try:
        res = supabase.table('user_profiles').select('points').eq('id', user_id).execute()
        return (res.data[0].get('points') or 0) if res.data else 0
    except:
        return 0

def award_points(user_id, action_type, points, description):
    try:
        supabase.table('points_ledger').insert({
            'user_id': user_id,
            'action_type': action_type,
            'points_earned': points,
            'description': description,
        }).execute()
        supabase.rpc('increment_user_points', {'p_user_id': user_id, 'p_points': points}).execute()
        return get_user_points(user_id)
    except:
        return None

def get_user_badge_stats(user_id):
    """Query saved_spots and compute all badge-check stats. Returns dict with 0s on failure."""
    _zero = {k: 0 for k in [
        'total_saves', 'total_chosen', 'wild_chosen', 'wild_idea_chosen',
        'rated_dining_4plus', 'wine_saves', 'brewery_saves', 'coffee_saves',
        'splurge_chosen', 'date_chosen', 'family_chosen', 'friends_chosen',
        'outdoor_chosen', 'hidden_gem_saves', 'culture_saves', 'event_chosen',
        'free_chosen', 'referral_count',
    ]}
    try:
        spots = supabase.table('saved_spots').select('*').eq('user_id', user_id).execute().data or []
        _t3_lower = {n.lower() for n in TIER_3_NAMES}

        def _cat(s):  return (s.get('category') or '').lower()
        def _chosen(s): return 'chosen' in (s.get('user_notes') or '').lower()

        stats = {
            'total_saves':       len(spots),
            'total_chosen':      sum(1 for s in spots if _chosen(s)),
            'wild_chosen':       sum(1 for s in spots if (s.get('mode') or '') == 'get_wild' and _chosen(s)),
            'wild_idea_chosen':  sum(1 for s in spots if (s.get('mode') or '') == 'wild_idea' and _chosen(s)),
            'rated_dining_4plus':sum(1 for s in spots if (s.get('rating') or 0) >= 4 and
                                   any(k in _cat(s) for k in ['restaurant','dining','bistro','kitchen','eatery','diner','cafe','brunch','food'])),
            'wine_saves':        sum(1 for s in spots if any(k in _cat(s) for k in ['wine','winery','vineyard'])),
            'brewery_saves':     sum(1 for s in spots if any(k in _cat(s) for k in ['brewery','brewing','taproom','brewpub'])),
            'coffee_saves':      sum(1 for s in spots if any(k in _cat(s) for k in ['coffee','cafe','espresso','tea'])),
            'splurge_chosen':    sum(1 for s in spots if (s.get('spend') or '') == '✨ Splurge' and _chosen(s)),
            'date_chosen':       sum(1 for s in spots if (s.get('group_type') or '') == 'Date' and _chosen(s)),
            'family_chosen':     sum(1 for s in spots if (s.get('group_type') or '') == 'Family Outing' and _chosen(s)),
            'friends_chosen':    sum(1 for s in spots if (s.get('group_type') or '') == 'Friends' and _chosen(s)),
            'outdoor_chosen':    sum(1 for s in spots if (s.get('setting') or '') == 'Outside' and _chosen(s)),
            'hidden_gem_saves':  sum(1 for s in spots if (s.get('tier_name') or '').lower() in _t3_lower),
            'culture_saves':     sum(1 for s in spots if any(k in _cat(s) for k in ['museum','gallery','art','theater','theatre','exhibit'])),
            'event_chosen':      sum(1 for s in spots if any(k in _cat(s) for k in ['event','concert','performing','music venue']) and _chosen(s)),
            'free_chosen':       sum(1 for s in spots if (s.get('spend') or '') == '🆓 Free' and _chosen(s)),
        }

        # Referral count via RPC
        try:
            _code = (supabase.table('user_profiles').select('referral_code').eq('id', user_id).execute().data or [{}])[0].get('referral_code', '')
            stats['referral_count'] = supabase.rpc('get_referral_count', {'p_referral_code': _code}).execute().data or 0
        except:
            stats['referral_count'] = 0

        return stats
    except:
        return _zero

def check_and_award_badges(user_id):
    try:
        stats  = get_user_badge_stats(user_id)
        earned = {b['badge_id'] for b in (supabase.table('badges').select('badge_id').eq('user_id', user_id).execute().data or [])}
        for badge in BADGES:
            if badge['id'] in earned:
                continue
            try:
                unlocked = badge['check'](stats)
            except:
                unlocked = False
            if unlocked:
                try:
                    supabase.table('badges').insert({
                        'user_id': user_id, 'badge_id': badge['id'],
                        'badge_name': badge['name'], 'badge_emoji': badge['emoji'],
                    }).execute()
                    award_points(user_id, 'badge', badge['pts'], f"Badge: {badge['name']}")
                    st.balloons()
                    st.success(f"🏆 Badge Unlocked: {badge['emoji']} {badge['name']}! +{badge['pts']} bonus points")
                except:
                    pass
    except:
        pass

def submit_feedback(user_id, comment):
    if not comment.strip():
        return False
    try:
        if not st.session_state.get('user'):
            screen = "login"
        elif st.session_state.get('show_onboarding'):
            screen = "onboarding"
        elif not st.session_state.get('search_active'):
            screen = "input"
        elif st.session_state.get('current_results'):
            screen = "results"
        else:
            screen = "loading"
        results = st.session_state.get('current_results')
        context = {
            "mem_loc":      st.session_state.get('mem_loc', ''),
            "mem_day":      st.session_state.get('mem_day', ''),
            "mem_time":     st.session_state.get('mem_time', ''),
            "mem_group":    st.session_state.get('mem_group', ''),
            "mem_vibe":     st.session_state.get('mem_vibe', ''),
            "mem_food":     st.session_state.get('mem_food', ''),
            "mem_dist":     st.session_state.get('mem_dist', 5),
            "mem_spec":     st.session_state.get('mem_spec', ''),
            "current_mode": st.session_state.get('current_mode'),
            "num_results":  len(results.get('recommendations', [])) if results else 0,
            "timed_out":    st.session_state.get('fetch_timed_out', False),
        }
        supabase.table('feedback').insert({
            'user_id': user_id,
            'screen': screen,
            'session_context': context,
            'comment': comment.strip(),
        }).execute()
        return True
    except Exception as e:
        return str(e)

def increment_wild_counter(city):
    try:
        today = datetime.utcnow().date().isoformat()
        supabase.rpc('increment_wild_counter', {'p_date': today, 'p_city': city}).execute()
    except:
        pass

def get_wild_count_today():
    try:
        today = datetime.utcnow().date().isoformat()
        res = supabase.table('wild_counter').select('count').eq('search_date', today).execute()
        if res.data:
            return sum(row['count'] for row in res.data)
        return 0
    except:
        return None

# ==========================================
# 4. HELPER FUNCTIONS (The Engine)
# ==========================================
def get_coordinates(location_query):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location_query}&key={GOOGLE_API_KEY}"
    try:
        response = requests.get(url, timeout=10).json()
        if response['status'] == 'OK':
            loc = response['results'][0]['geometry']['location']
            return loc['lat'], loc['lng']
    except: pass
    return None, None

@st.cache_data(ttl=86400)
def get_local_target_date(lat, lng, day_choice):
    timestamp = int(time.time())
    url = f"https://maps.googleapis.com/maps/api/timezone/json?location={lat},{lng}&timestamp={timestamp}&key={GOOGLE_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if res['status'] == 'OK':
            local_timestamp = timestamp + res['dstOffset'] + res['rawOffset']
            local_time = datetime.utcfromtimestamp(local_timestamp)
        else:
            local_time = datetime.utcnow()
    except:
        local_time = datetime.utcnow()
        
    if "Tomorrow" in day_choice:
        target_date = local_time + timedelta(days=1)
        return target_date.strftime("%A, %B %d, %Y"), "TOMORROW"
    else:
        return local_time.strftime("%A, %B %d, %Y"), "TODAY"

def get_state_from_coords(lat, lng):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={GOOGLE_API_KEY}"
    try:
        res = requests.get(url, timeout=10).json()
        if res['status'] == 'OK':
            for component in res['results'][0]['address_components']:
                if 'administrative_area_level_1' in component['types']:
                    return component['short_name'], component['long_name']
    except:
        pass
    return None, None

def get_live_weather(lat, lng):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lng}&units=imperial&appid={OPENWEATHER_API_KEY}"
        res = requests.get(url, timeout=10).json()
        if res.get("cod") == 200:
            return f"{res['main']['temp']}°F and {res['weather'][0]['description']}"
    except: pass
    return "Weather data unavailable."

def build_semantic_query(filters_dict, profile, preference_scores=None, mode=None):
    specific = (filters_dict.get('specific') or "").strip()
    vibe  = filters_dict.get('vibe', "Doesn't Matter")
    food  = filters_dict.get('food', 'Full Meal')
    group = filters_dict.get('group', '')
    spend = filters_dict.get('spend', '💰 Moderate')
    is_get_wild = (mode == "get_wild")

    # Activity keyword triggers — override base query entirely
    _ACTIVITY_TRIGGERS = [
        ({"hike", "hiking"},              "hiking trails trailheads nature walks"),
        ({"bike", "biking", "cycling"},   "bike trails cycling paths greenways"),
        ({"kayak", "paddle", "canoe"},    "kayak rental canoe paddle water sports"),
        ({"climb", "climbing"},           "rock climbing gym bouldering climbing wall"),
        ({"axe"},                         "axe throwing venue"),
        ({"escape"},                      "escape room puzzle room"),
        ({"pottery", "ceramics"},         "pottery studio ceramics class art studio"),
        ({"comedy"},                      "comedy club stand up improv"),
        ({"trivia"},                      "trivia night bar pub quiz"),
        ({"karaoke"},                     "karaoke bar singing venue"),
    ]

    # If specific keyword provided, it drives the query
    if specific:
        _spec_lower = specific.lower()
        # Check activity keyword triggers first (highest priority)
        for _kws, _override in _ACTIVITY_TRIGGERS:
            if any(kw in _spec_lower for kw in _kws):
                return _override
        loc_hint = {"Date": "intimate", "Family Outing": "family-friendly", "Friends": "lively"}.get(group, "")
        # Check if specific matches a known non-traditional type and boost it
        _nt_match = next(
            (t for t in NON_TRADITIONAL_INDOOR + NON_TRADITIONAL_OUTDOOR if t in _spec_lower or _spec_lower in t),
            None
        )
        if _nt_match:
            return f"{_nt_match} {specific} near me {loc_hint}".strip()
        parts = [f"{specific} venues", f"{specific} bars" if "bar" not in specific.lower() else "", loc_hint]
        return " ".join(p for p in parts if p).strip()

    modifiers = []
    # Boost top 2 learned taste keywords (skip avoid list)
    if preference_scores:
        avoid = set(preference_scores.get('avoid_keywords') or [])
        for kw in (preference_scores.get('top_keywords') or [])[:2]:
            if kw not in avoid:
                modifiers.append(kw)

    if profile:
        if profile.get('needs_dog_friendly') and vibe == "Outside": modifiers.append("dog-friendly")
        if profile.get('vibe_preference'): modifiers.append(profile.get('vibe_preference'))

    if group == "Date": modifiers.append("intimate")
    elif group == "Family Outing": modifiers.append("kid-friendly")
    elif group == "Friends": modifiers.append("lively")

    no_food = food == "No Food Needed"
    is_free = spend == "🆓 Free"

    # Free budget: override all other query logic — only genuinely free venues
    if is_free:
        if vibe == "Outside":
            return "free park free trail free nature area free waterfront free botanical garden public plaza"
        elif vibe == "Inside":
            return "free museum free art gallery free library free community center free indoor attraction"
        else:
            return "free park free museum free trail free public attraction no admission free community event"

    # Full Meal anchor: always return a restaurant-focused query (overrides vibe-based branching)
    if food == "Full Meal":
        _fm_group_map = {
            "Family Outing": "family restaurant kid friendly dining",
            "Date":          "romantic restaurant fine dining intimate",
            "Friends":       "lively restaurant group dining social",
            "Solo":          "restaurant bar solo dining counter seating",
        }
        _fm_base = _fm_group_map.get(group, "restaurant dining local eats")
        if spend == "✨ Splurge":
            _fm_base = f"upscale restaurant fine dining tasting menu {_fm_base}"
        if vibe == "Outside":
            _fm_base = f"outdoor dining patio restaurant {_fm_base}"
        elif vibe == "Inside":
            _fm_base = f"cozy restaurant indoor dining {_fm_base}"
        return _fm_base.strip()

    # Base query by vibe + food + spend (randomized for freshness)
    if vibe == "Outside":
        if is_free:
            base = "free parks hiking trails nature reserves free outdoor spaces scenic viewpoints"
        elif food == "Full Meal":
            base = random.choice([
                "restaurants with scenic views outdoor dining",
                "farm to table restaurants with outdoor seating",
                "waterfront dining outdoor patios",
                "winery vineyard outdoor dining",
                "rooftop restaurants with views",
            ])
        elif food == "Just Drinks/Coffee":
            base = random.choice([
                "outdoor bars with views beer gardens patios",
                "wineries with outdoor seating",
                "rooftop bars outdoor cocktail venues",
                "breweries with outdoor spaces",
            ])
        else:
            base = random.choice([
                "hiking trails nature trails scenic walks",
                "bike trails greenways riverside paths",
                "botanical gardens arboretums nature preserves",
                "scenic overlooks viewpoints hidden natural spots",
                "kayak canoe paddleboard rental outdoor water activities",
                "rock climbing outdoor climbing walls bouldering",
                "disc golf ultimate frisbee outdoor recreation",
                "farms orchards agritourism outdoor experiences",
            ])
    elif vibe == "Inside":
        if is_free:
            base = "free museums free art galleries free community spaces free attractions"
        elif food == "Full Meal":
            base = random.choice([
                "highly rated restaurants unique dining experiences",
                "chef driven restaurants local cuisine",
                "immersive dining experiences unique restaurants",
                "farm to table restaurants locally sourced",
            ])
        elif food == "Just Drinks/Coffee":
            base = random.choice([
                "wine bars speakeasies cocktail lounges",
                "craft cocktail bars hidden bars",
                "whiskey bars wine bars tasting rooms",
            ])
        else:
            base = random.choice([
                "escape rooms puzzle rooms immersive experiences",
                "axe throwing bowling arcade bars entertainment",
                "pottery studios art classes paint and sip",
                "comedy clubs improv theaters live entertainment",
                "climbing gyms trampoline parks active entertainment",
                "board game cafes trivia nights social games",
                "cooking classes culinary experiences food tours",
                "virtual reality arcades gaming lounges",
            ])
    else:  # Doesn't Matter
        if is_free:
            base = "free activities free entertainment free museums free parks"
        elif food == "Full Meal":
            base = random.choice([
                "highly rated restaurants unique dining experiences",
                "chef driven restaurants local cuisine",
                "immersive dining experiences unique restaurants",
            ])
        elif food == "Just Drinks/Coffee":
            base = "wine bars speakeasies lounges cocktail bars"
        else:
            base = random.choice([
                "museums parks entertainment venues unique attractions",
                "outdoor experiences unique activities local favorites",
                "escape rooms art galleries parks unique venues",
            ])

    # Spend-level suffix modifiers
    if is_free:
        modifiers.append("free admission no cover charge")
    elif spend == "✨ Splurge":
        if group == "Date":
            base = "michelin star fine dining tasting menu upscale cocktail lounge"
        else:
            modifiers.append("upscale fine dining luxury high-end rooftop")

    # Non-traditional venue injection
    if is_get_wild:
        # Maximum spontaneity — sample from both lists
        modifiers.append(" ".join(random.sample(NON_TRADITIONAL_INDOOR, 2)))
        modifiers.append(" ".join(random.sample(NON_TRADITIONAL_OUTDOOR, 2)))
    elif no_food:
        if vibe == "Inside":
            modifiers.append(" ".join(random.sample(NON_TRADITIONAL_INDOOR, 3)))
        elif vibe == "Outside":
            modifiers.append(" ".join(random.sample(NON_TRADITIONAL_OUTDOOR, 3)))
        else:
            modifiers.append(" ".join(random.sample(NON_TRADITIONAL_INDOOR, 2)))
            modifiers.append(" ".join(random.sample(NON_TRADITIONAL_OUTDOOR, 1)))
        modifiers.append("pop-up temporary installation")
    elif food == "Just Drinks/Coffee" and group in ("Friends", "Date"):
        modifiers.append("axe throwing bowling karaoke arcade bar")
    elif food != "Full Meal" and group in ("Date", "Friends"):
        modifiers.append(" ".join(random.sample(NON_TRADITIONAL_INDOOR, 2)))

    exclusion = " NOT bar NOT brewery NOT restaurant NOT cafe" if no_food else ""
    modifier_str = " ".join(modifiers)
    return f"{modifier_str} {base}{exclusion}".strip()

def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

_JUST_OPENED_KWS = {"new", "just opened", "grand opening", "opening soon",
                    "soft launch", "pop-up", "popup", "newly opened"}

def _process_places(places, lat, lng, threshold, freshness_boost=False):
    """Process raw Places API results: add photo_url, distance_miles, just_opened flags."""
    out = []
    for place in places:
        photos = place.get('photos', [])
        if photos:
            photo_name = photos[0].get('name', '')
            place['photo_ref'] = photo_name
            place['photo_url'] = f"https://places.googleapis.com/v1/{photo_name}/media?key={GOOGLE_API_KEY}&maxHeightPx=400&maxWidthPx=800"
        else:
            place['photo_ref'] = None
            place['photo_url'] = None
        loc = place.get('location', {})
        plat, plng = loc.get('latitude'), loc.get('longitude')
        if plat and plng:
            dist = haversine_miles(lat, lng, plat, plng)
            place['distance_miles'] = round(dist, 1)
            if dist > threshold:
                continue
        if freshness_boost:
            place['freshness_boost'] = True
        _text = " ".join([
            (place.get('displayName', {}).get('text') or '').lower(),
            (place.get('editorialSummary', {}).get('text') or '').lower(),
        ])
        if any(kw in _text for kw in _JUST_OPENED_KWS):
            place['just_opened'] = True
        out.append(place)
    return out

def _run_places_query(text_query, lat, lng, radius_miles, page_size=8):
    """Single Google Places text search call. Returns raw place dicts."""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.priceLevel,places.currentOpeningHours,places.websiteUri,places.photos,places.editorialSummary,places.location"
    }
    radius_meters = int(radius_miles * 1609.34)
    try:
        response = requests.post(url, headers=headers, json={
            "textQuery": text_query,
            "pageSize": page_size,
            "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_meters}}
        }, timeout=15)
        if response.status_code == 200:
            return response.json().get('places', [])
    except:
        pass
    return []

_OUTDOOR_QUERY_POOL = [
    "hiking trail nature trail scenic walk",
    "bike trail greenway rail trail cycling path",
    "scenic overlook viewpoint panoramic view",
    "nature preserve wildlife area conservation area",
    "waterfall swimming hole natural swimming area",
    "botanical garden arboretum nature park",
    "kayak canoe rental water sports outdoor",
    "rock climbing bouldering outdoor climbing",
]

def fetch_places_semantic(semantic_query, lat, lng, radius_miles, vibe="", food=""):
    threshold = radius_miles * 1.5

    main_places  = _run_places_query(semantic_query, lat, lng, radius_miles, page_size=12)
    fresh_places = _run_places_query("new opening pop-up unique hidden", lat, lng, radius_miles, page_size=3)

    # Secondary outdoor queries when context calls for it
    outdoor_extra = []
    if vibe == "Outside" and food == "No Food Needed":
        for q in random.sample(_OUTDOOR_QUERY_POOL, 2):
            outdoor_extra.extend(_run_places_query(q, lat, lng, radius_miles, page_size=3))

    seen_names = set()
    result = []
    for p in _process_places(main_places, lat, lng, threshold, freshness_boost=False):
        name = (p.get('displayName', {}).get('text') or '').lower()
        seen_names.add(name)
        result.append(p)
    for p in _process_places(fresh_places, lat, lng, threshold, freshness_boost=True):
        name = (p.get('displayName', {}).get('text') or '').lower()
        if name and name not in seen_names:
            seen_names.add(name)
            result.append(p)
    for p in _process_places(outdoor_extra, lat, lng, threshold, freshness_boost=False):
        name = (p.get('displayName', {}).get('text') or '').lower()
        if name and name not in seen_names:
            p['outdoor_boost'] = True
            seen_names.add(name)
            result.append(p)
    return result

def build_tier_queries(filters_dict, profile=None, preference_scores=None):
    """Build 3 tier-specific Place queries for parallel fetching.
    Returns (t1_query, t2_query, t3_query):
      - tier1: reliable, crowd-pleasing spots (highly-rated, established)
      - tier2: fresh, interesting picks (new, trending, unique)
      - tier3: hidden gems (unconventional, lesser-known, quirky)
    """
    vibe    = filters_dict.get('vibe', "Doesn't Matter")
    food    = filters_dict.get('food', 'Full Meal')
    group   = filters_dict.get('group', '')
    spend   = filters_dict.get('spend', '💰 Moderate')
    specific = (filters_dict.get('specific') or '').strip()
    is_free  = (spend == "🆓 Free")

    _gm = {"Date": "intimate romantic", "Family Outing": "family friendly kid-friendly",
           "Friends": "lively group social", "Solo": "solo-friendly"}.get(group, "")

    # Specific keyword: all 3 tiers target it, differentiated by quality signal
    if specific:
        return (
            f"popular well-rated {specific} {_gm}".strip(),
            f"new unique {specific} {_gm}".strip(),
            f"hidden local {specific} {_gm}".strip(),
        )

    # Free budget: all tiers target free venues
    if is_free:
        if vibe == "Outside":
            base = "free park trail nature area waterfront public plaza"
        elif vibe == "Inside":
            base = "free museum art gallery library community center"
        else:
            base = "free park museum trail public attraction community event"
        return (
            f"popular well-known {base}".strip(),
            f"interesting unique {base}".strip(),
            f"secret off the beaten path {base} local gem".strip(),
        )

    # Full Meal: all tiers target restaurants, differentiated by angle
    if food == "Full Meal":
        _fm_map = {
            "Family Outing": "family restaurant kid friendly dining",
            "Date":          "romantic restaurant fine dining intimate",
            "Friends":       "lively restaurant group dining social",
            "Solo":          "restaurant solo dining counter seating",
        }
        base_type = _fm_map.get(group, "restaurant dining local eats")
        splurge = (spend == "✨ Splurge")
        out_pfx = "outdoor dining patio " if vibe == "Outside" else ("cozy indoor " if vibe == "Inside" else "")
        t1 = f"{'upscale michelin ' if splurge else 'popular highly rated '}{out_pfx}{base_type} {_gm}".strip()
        t2 = f"new trending interesting cuisine {out_pfx}{base_type} chef driven {_gm}".strip()
        t3 = f"hidden gem local secret hole-in-the-wall {out_pfx}{base_type} {_gm}".strip()
        return (t1, t2, t3)

    # Just Drinks/Coffee
    if food == "Just Drinks/Coffee":
        if vibe == "Outside":
            return (
                f"popular outdoor bar beer garden brewery patio {_gm}".strip(),
                f"rooftop bar unique outdoor cocktails wine bar {_gm}".strip(),
                f"hidden local craft cocktail speakeasy secret bar {_gm}".strip(),
            )
        elif vibe == "Inside":
            return (
                f"popular cocktail bar wine bar craft brewery {_gm}".strip(),
                f"unique cocktail lounge wine tasting room interesting bar {_gm}".strip(),
                f"hidden speakeasy secret bar local craft cocktail {_gm}".strip(),
            )
        else:
            return (
                f"popular bar cocktail lounge brewery wine bar {_gm}".strip(),
                f"unique rooftop bar wine bar speakeasy interesting cocktails {_gm}".strip(),
                f"hidden speakeasy secret bar local craft cocktail gem {_gm}".strip(),
            )

    # No Food Needed
    if vibe == "Outside":
        return (
            f"popular park hiking trail nature preserve outdoor recreation {_gm}".strip(),
            f"unique outdoor activity botanical garden scenic overlook kayaking {_gm}".strip(),
            f"hidden nature trail waterfall swimming hole secret outdoor gem {_gm}".strip(),
        )
    elif vibe == "Inside":
        return (
            f"popular entertainment museum art gallery indoor attraction {_gm}".strip(),
            f"escape room axe throwing pottery class unique entertainment {_gm}".strip(),
            f"hidden local speakeasy underground niche experience secret venue {_gm}".strip(),
        )
    else:
        return (
            f"popular local attraction museum park entertainment venue {_gm}".strip(),
            f"unique interesting escape room art gallery brewery activity {_gm}".strip(),
            f"hidden gem off the beaten path local secret niche unusual activity {_gm}".strip(),
        )

def fetch_tier_places(t1_query, t2_query, t3_query, lat, lng, radius_miles):
    """Fetch 3 tiers of Places results in parallel. Returns {'tier1': [...], 'tier2': [...], 'tier3': [...]}."""
    from concurrent.futures import ThreadPoolExecutor
    threshold = radius_miles * 1.5

    def _fetch(query, page_size, freshness_boost):
        raw = _run_places_query(query, lat, lng, radius_miles, page_size=page_size)
        return _process_places(raw, lat, lng, threshold, freshness_boost=freshness_boost)

    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(_fetch, t1_query, 10, False)
        f2 = executor.submit(_fetch, t2_query, 8,  False)
        f3 = executor.submit(_fetch, t3_query, 8,  True)   # freshness_boost flags tier 3 results
        tier1 = f1.result()
        tier2 = f2.result()
        tier3 = f3.result()

    # Deduplicate across tiers — tier1 has priority
    seen = {(p.get('displayName', {}).get('text') or '').lower() for p in tier1}
    tier2 = [p for p in tier2 if (p.get('displayName', {}).get('text') or '').lower() not in seen]
    seen.update((p.get('displayName', {}).get('text') or '').lower() for p in tier2)
    tier3 = [p for p in tier3 if (p.get('displayName', {}).get('text') or '').lower() not in seen]

    return {'tier1': tier1, 'tier2': tier2, 'tier3': tier3}

_TM_CLASSIFICATION_MAP = {
    "music":           ("music",        None),
    "live music":      ("music",        None),
    "concert":         ("music",        None),
    "band":            ("music",        None),
    "sports":          ("sports",       None),
    "game":            ("sports",       None),
    "basketball":      ("sports",       None),
    "football":        ("sports",       None),
    "baseball":        ("sports",       None),
    "hockey":          ("sports",       None),
    "soccer":          ("sports",       None),
    "comedy":          ("arts & theatre", "comedy"),
    "stand-up":        ("arts & theatre", "comedy"),
    "stand up":        ("arts & theatre", "comedy"),
    "comedian":        ("arts & theatre", "comedy"),
    "theater":         ("arts & theatre", None),
    "theatre":         ("arts & theatre", None),
    "broadway":        ("arts & theatre", None),
    "show":            ("arts & theatre", None),
    "play":            ("arts & theatre", None),
    "family":          ("family",       None),
    "kids":            ("family",       None),
    "festival":        ("music",        "festival"),
    "outdoor concert": ("music",        "festival"),
}

def fetch_live_events(lat, lng, radius_miles, target_date_str, specific_keyword=""):
    try:
        target_date = datetime.strptime(target_date_str, "%A, %B %d, %Y").date()
        start_dt = f"{target_date.isoformat()}T00:00:00Z"
        end_dt   = f"{(target_date + timedelta(days=1)).isoformat()}T00:00:00Z"

        kw_lower = (specific_keyword or "").lower().strip()
        classification, extra_keyword = _TM_CLASSIFICATION_MAP.get(kw_lower, (None, None))

        params = {
            "apikey":        TICKETMASTER_API_KEY,
            "latlong":       f"{lat},{lng}",
            "radius":        int(radius_miles),
            "unit":          "miles",
            "startDateTime": start_dt,
            "endDateTime":   end_dt,
            "size":          5,
            "countryCode":   "US",
            "sort":          "relevance,desc",
        }
        if classification:
            params["classificationName"] = classification
        if extra_keyword:
            params["keyword"] = extra_keyword
        elif kw_lower and not classification:
            # No category match — pass the raw keyword for TM to search by
            params["keyword"] = specific_keyword.strip()

        response = requests.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params=params,
            timeout=5,
        )
        if response.status_code != 200:
            return []

        events_raw = response.json().get('_embedded', {}).get('events', [])
        results = []

        for ev in events_raw:
            venue = (ev.get('_embedded', {}).get('venues') or [{}])[0]
            addr_parts = [
                venue.get('address', {}).get('line1', ''),
                venue.get('city', {}).get('name', ''),
                venue.get('state', {}).get('stateCode', ''),
            ]
            venue_address = ', '.join(p for p in addr_parts if p)

            start      = ev.get('dates', {}).get('start', {})
            local_date = start.get('localDate', '')
            try:
                date_label = datetime.strptime(local_date, "%Y-%m-%d").strftime("%B %d, %Y")
            except:
                date_label = local_date

            raw_time = start.get('localTime', '')
            if raw_time:
                try:
                    dt = datetime.strptime(raw_time, "%H:%M:%S")
                    hour = dt.hour % 12 or 12
                    start_time = f"{hour}:{dt.strftime('%M')} {'AM' if dt.hour < 12 else 'PM'}"
                except:
                    start_time = raw_time
            else:
                start_time = "Time TBD"

            images    = ev.get('images', [])
            image_url = next(
                (img['url'] for img in images if img.get('ratio') == '16_9' and img.get('width', 0) > 500),
                images[0]['url'] if images else None
            )

            results.append({
                "title":         ev.get('name', ''),
                "venue_name":    venue.get('name', ''),
                "venue_address": venue_address,
                "date_str":      date_label,
                "start_time":    start_time,
                "date_verified": True,
                "url":           ev.get('url', ''),
                "image_url":     image_url,
                "snippet":       (ev.get('info') or ev.get('pleaseNote') or '')[:500],
            })

        return results
    except:
        return []

def _should_show_wild_idea_teaser():
    """Show the teaser banner whenever not dismissed this session.
    No cooldown check — only generation is cooldown-gated."""
    return not st.session_state.get('wild_idea_dismissed')

def _should_generate_wild_idea(user_profile):
    """Full check: has location AND hasn't been generated in 4 h."""
    if not st.session_state.get('mem_gps_active') and not st.session_state.get('mem_loc'):
        return False
    last_str = (user_profile or {}).get('last_wild_idea_at')
    if last_str:
        try:
            last_dt = datetime.fromisoformat(last_str[:19])
            if datetime.utcnow() - last_dt < timedelta(hours=4):
                return False
        except:
            pass
    return True

def _dismiss_wild_idea(user_id):
    st.session_state.wild_idea_dismissed = True
    try:
        supabase.table('user_profiles').update(
            {'last_wild_idea_at': datetime.utcnow().isoformat()}
        ).eq('id', user_id).execute()
    except:
        pass

@st.cache_data(ttl=14400)
def get_wild_idea(user_id_str, lat, lng, location_name, profile_summary, pref_keywords=None, radius_miles=20):
    """Returns a full card-ready dict or None. Uses real Google Places data. Cached 4h."""
    try:
        h = datetime.utcnow().hour
        if 6 <= h < 12:       time_context = "morning"
        elif 12 <= h < 17:    time_context = "afternoon"
        elif 17 <= h < 21:    time_context = "evening"
        else:                 time_context = "late night"

        # Build Places query — personalized by top preference keyword if available
        kw_prefix = f"unique {pref_keywords[0]}" if pref_keywords else "unique hidden"
        places_query = f"{kw_prefix} local experience {location_name}"

        # Fetch real Places results
        raw_places = fetch_places_semantic(places_query, lat, lng, radius_miles)
        if not raw_places:
            return None

        # Build a slim candidate list for GPT (name + category hint only)
        candidates = []
        for p in raw_places[:5]:
            candidates.append({
                "name":     (p.get('displayName', {}).get('text') or ''),
                "summary":  (p.get('editorialSummary', {}).get('text') or ''),
                "address":  (p.get('formattedAddress') or ''),
            })

        # Ask GPT to pick the most surprising option from real data
        client = OpenAI(api_key=OPENAI_API_KEY)
        pref_clause = (
            f" for someone who enjoys {profile_summary}"
            if profile_summary and profile_summary != "no specific preferences" else ""
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": (
                f"From this list of real local venues near {location_name}, pick the ONE most "
                f"surprising and delightful option for a {time_context} outing{pref_clause}. "
                "Prefer unconventional, unique, or hidden gems over mainstream choices. "
                f"Venues: {json.dumps(candidates)}. "
                "Return JSON: name (exact venue name from the list), "
                "category (concise venue type, e.g. 'Escape Room', 'Jazz Club'), "
                "why_now (one punchy why-this-why-tonight sentence, max 15 words), "
                "emoji (single emoji), "
                "matched_tags (array of 2-3 short descriptor strings)."
            )}],
            max_tokens=200,
            timeout=10,
        )
        data = json.loads(response.choices[0].message.content.strip())
        if not data.get('name') or not data.get('why_now'):
            return None

        # Match chosen name back to real Places data for address, website, photo
        chosen_name = (data['name'] or '').lower().strip()
        matched = next(
            (p for p in raw_places[:5]
             if chosen_name in (p.get('displayName', {}).get('text') or '').lower()),
            raw_places[0]
        )
        data['address']  = matched.get('formattedAddress') or ''
        data['website']  = matched.get('websiteUri') or ''
        data['photo_url'] = matched.get('photo_url')
        data['vibe_check'] = ''

        if not isinstance(data.get('matched_tags'), list):
            data['matched_tags'] = []
        if not data.get('emoji'):
            data['emoji'] = '🎲'
        if not data.get('category'):
            data['category'] = ''

        return data
    except:
        pass
    return None

def render_wild_idea_card(idea, location_input, user_id):
    """Renders the wild idea as a full result card, matching render_spot_card() layout."""
    name     = idea.get('name', 'Wild Idea')
    category = idea.get('category', '')
    why_now  = idea.get('why_now', '')
    emoji    = idea.get('emoji', '🎲')
    address  = idea.get('address', '')
    website  = idea.get('website', '') or ''
    vibe     = idea.get('vibe_check', '')
    tags     = idea.get('matched_tags', [])

    img_url = idea.get('photo_url') or get_fallback_image(category, why_now)

    # Tags
    tags_html = ''
    if isinstance(tags, list):
        for tag in tags[:3]:
            tags_html += f'<span class="wc-tag">✓ {tag}</span>'

    # Vibe pills (matches render_spot_card)
    _vibe_words = [w.strip() for w in vibe.split(',') if w.strip()] if vibe else []
    if _vibe_words:
        _pills = [f'<span class="wc-vibe-pill">{"✨ " if i == 0 else ""}{w}</span>'
                  for i, w in enumerate(_vibe_words)]
        vibe_pills_html = '<div class="wc-vibe-row">' + ''.join(_pills) + '</div>'
    else:
        vibe_pills_html = ''

    # Full utility row (matches render_spot_card)
    search_q       = urllib.parse.quote(f"{name} {location_input}")
    map_url        = f"https://www.google.com/maps/search/?api=1&query={search_q}"
    encoded_addr   = urllib.parse.quote(address) if address else ''
    uber_url       = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_addr}"
    share_text     = f"Let's go to {name}! {address}\n{map_url}"
    share_encoded  = urllib.parse.quote(share_text)
    share_subj_enc = urllib.parse.quote(f"Wild Plan: {name}")
    share_body_enc = urllib.parse.quote(share_text)
    sep = '<span class="wc-util-sep">|</span>'
    website_part = f'<a href="{website}" target="_blank" class="wc-util-link">🌐 Website</a>{sep}' if website else ''
    utility_html = (
        f'<div class="wc-utility">'
        f'{website_part}'
        f'<a href="{map_url}" target="_blank" class="wc-util-link">🗺️ Directions</a>{sep}'
        f'<a href="{uber_url}" target="_blank" class="wc-util-link">🚗 Uber</a>{sep}'
        f'<a href="sms:?body={share_encoded}" class="wc-util-link">📱 Text</a>{sep}'
        f'<a href="mailto:?subject={share_subj_enc}&body={share_body_enc}" class="wc-util-link">📧 Email</a>'
        f'</div>'
    )
    addr_html = f'<div class="wc-address">📍 {address}</div>' if address else ''

    html_card = f"""<div class="wc-shell">
  <div class="wc-img-wrap">
    <img src="{img_url}" class="wc-img" alt="">
    <div class="wc-tier" style="border-left: 3px solid #2d6a4f;">✦ Wild Idea</div>
  </div>
  <div class="wc-body">
    <div class="wc-name">{emoji} {name}</div>
    <div class="wc-meta">{category}</div>
    {vibe_pills_html}{addr_html}
    {utility_html}
    <hr class="wc-hr">
    <p class="wc-pitch">{why_now}</p>
    <div class="wc-tags">{tags_html}</div>
  </div>
</div>"""

    with st.container(border=True):
        st.markdown(html_card, unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        _key = name.replace(' ', '_')[:20]
        _wi_ctx = dict(
            mode='wild_idea',
            group_type=st.session_state.get('mem_group', ''),
            setting=st.session_state.get('mem_vibe', ''),
            spend=st.session_state.get('mem_spend', ''),
            tier_name='Wild Idea',
        )
        with col1:
            if st.button("⭐ Save for Later", key=f"wi_save_{_key}", use_container_width=True):
                _pre = save_spot_to_db(user_id, name, address, category, **_wi_ctx)
                _pts = POINTS['first_save'] if _pre == 0 else POINTS['save']
                award_points(user_id, "save", _pts, "First spot saved! 🎉" if _pre == 0 else "Saved a Wild Idea spot")
                check_and_award_badges(user_id)
                st.session_state.wild_idea_expanded = False
                st.rerun()
        with col2:
            if st.button("✅ I'm Going", key=f"wi_going_{_key}", use_container_width=True, type="primary"):
                save_spot_to_db(user_id, name, address, category, notes="chosen", **_wi_ctx)
                award_points(user_id, "going", POINTS['wild_idea'], f"🎲 Wild Idea accepted! +{POINTS['wild_idea']} points")
                check_and_award_badges(user_id)
                st.session_state.wild_idea_expanded = False
                st.balloons()
                st.rerun()
        with col3:
            if st.button("✕ Not for me", key=f"wi_nope_{_key}", use_container_width=True):
                _dismiss_wild_idea(user_id)
                st.rerun()

    st.markdown(
        '<p style="text-align:center;color:#9ca3af;font-size:0.78rem;margin-top:2px;">'
        '✨ Check back — ideas get better as you get more wild</p>',
        unsafe_allow_html=True,
    )


# NOTE: Eventbrite supplemental events source was evaluated and skipped.
# Eventbrite's public event search API (GET /v3/events/search/ with lat/lng radius)
# was permanently removed on Feb 20, 2020. As of 2025 the API is effectively
# unsupported — no global search endpoint exists on any tier. Skip unless
# Eventbrite introduces a new discovery API.

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3), retry=retry_if_not_exception_type(TimeoutError))
def get_ai_recommendations(places_data, live_events_data, weather_report, filters_dict, location_name, target_date_str, relative_day, profile, excluded_spots, favorite_spots, mode="top_3", lat=None, lng=None, radius_miles=20, preference_scores=None):
    client = OpenAI(api_key=OPENAI_API_KEY)

    _spend_filter = filters_dict.get('spend', '💰 Moderate')
    _PAID_LEVELS = {"PRICE_LEVEL_MODERATE", "PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"}
    _PREMIUM_LEVELS = {"PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"}
    _excl_lower = {s.lower().strip() for s in (excluded_spots or [])}

    def _filter_tier(places):
        if _spend_filter == "🆓 Free":
            places = [p for p in places if p.get('priceLevel') not in _PAID_LEVELS]
        elif _spend_filter == "✨ Splurge":
            places = sorted(places, key=lambda p: 0 if p.get('priceLevel') in _PREMIUM_LEVELS else 1)
        if _excl_lower:
            places = [p for p in places if not any(
                ex in (p.get('displayName', {}).get('text', '') or '').lower() for ex in _excl_lower
            )]
        return places

    _is_tiered = isinstance(places_data, dict)
    if _is_tiered:
        trimmed_t1 = _filter_tier(places_data.get('tier1', []))[:5]
        trimmed_t2 = _filter_tier(places_data.get('tier2', []))[:5]
        trimmed_t3 = _filter_tier(places_data.get('tier3', []))[:5]
        trimmed_places = None  # not used in tiered mode
    else:
        trimmed_places = _filter_tier(list(places_data) if places_data else [])[:8]
    # Python-level events gate — AI never sees events when food=Full Meal
    _food_filter = filters_dict.get('food', '')
    if _food_filter == 'Full Meal':
        safe_events_data = []  # hard gate: no events, regardless of what was fetched
    elif isinstance(live_events_data, list):
        safe_events_data = live_events_data[:1]  # cap at 1 event to prevent AI over-indexing
    elif isinstance(live_events_data, str):
        safe_events_data = live_events_data[:4000]
    else:
        safe_events_data = []

    profile_context = ""
    if profile:
        stroller = "MUST be stroller accessible." if profile.get('needs_stroller_access') else ""
        dog = "MUST be dog-friendly." if profile.get('needs_dog_friendly') and filters_dict['vibe'] == "Outside" else ""
        vibe_pref = f"Prioritize locations matching this vibe: {profile.get('vibe_preference')}." if profile.get('vibe_preference') else ""
        nonalc = "NEVER recommend bars, breweries, cocktail bars, or any alcohol-focused venue." if profile.get('needs_nonalcoholic') else ""
        restrictions = profile.get('dietary_restrictions', '')
        dietary = f"User dietary restrictions: {restrictions}. Only recommend venues that can accommodate these." if restrictions and restrictions.strip() else ""
        history_context = f"\nUSER'S HISTORICAL FAVORITES (Learn from their taste!): {', '.join(favorite_spots)}" if favorite_spots else ""
        profile_context = f"\nUSER BASELINE PROFILE:\n{stroller}\n{dog}\n{vibe_pref}\n{nonalc}\n{dietary}{history_context}"

    blacklist_context = (
        f"⚠️ HARD EXCLUSION — These venues have already been shown or saved. "
        f"They are BANNED from your output. Do NOT recommend them under any circumstances: "
        f"{', '.join(excluded_spots)}"
    ) if excluded_spots else ""

    taste_context = ""
    if preference_scores and preference_scores.get('rated_count', 0) >= 2:
        _count = preference_scores['rated_count']
        _kws = preference_scores.get('top_keywords') or []
        _cats = preference_scores.get('top_categories') or []
        _parts = []
        if _kws: _parts.append(f"Consistently enjoys: {', '.join(_kws)}")
        if _cats: _parts.append(f"Top rated categories: {', '.join(_cats)}")
        if _parts:
            taste_context = (
                f"\nUSER TASTE PROFILE (learned from {_count} saved spots):\n"
                + "\n".join(_parts)
                + "\nUse this to break ties between equally good options — lean toward what they've historically loved."
            )

    if mode == "get_wild":
        instruction = """Select EXACTLY ONE option from the data. Assign it the category: 'Spontaneous Adventure'."""
    else:
        _t1 = random.choice(TIER_1_NAMES)
        _t2 = random.choice(TIER_2_NAMES)
        _t3 = random.choice(TIER_3_NAMES)
        if _is_tiered:
            instruction = f"""
        Return EXACTLY 3 recommendations, one from each TIER DATA section:
        1. '{_t1}' — use a result from TIER 1 DATA (highly-rated, established, crowd-pleasing).
        2. '{_t2}' — use a result from TIER 2 DATA (new, trending, interesting, or unique).
        3. '{_t3}' — use a result from TIER 3 DATA (hidden, unconventional, lesser-known).
        STRICT RULE: Each recommendation MUST come from its designated tier. If a tier's data is empty, use the best match from any tier.
            """
        else:
            instruction = f"""
        Return EXACTLY 3 options from the data, providing STRICT VARIETY.
        Assign each to one of these tier_name labels: '{_t1}', '{_t2}', '{_t3}'.
            """

    _vibe = filters_dict.get('vibe', '')
    _wr = (weather_report or "").lower()
    _bad_weather = any(w in _wr for w in ("rain", "snow", "storm")) or any(
        f"{t}°f" in _wr for t in range(0, 45)
    ) or ("°f" in _wr and any(
        int(tok.replace("°f", "")) < 45
        for tok in _wr.split()
        if tok.replace("°f", "").lstrip("-").isdigit()
    ))
    if _vibe == "Inside":
        weather_rule = "4. WEATHER: User wants indoors — no weather restrictions apply."
    elif _vibe == "Outside" and _bad_weather:
        weather_rule = (
            f"4. WEATHER ALERT: {weather_report}. User selected Outside but conditions are poor. "
            "Strongly prefer indoor or covered venues. Outdoor-only venues (beer gardens, rooftop bars, "
            "open patios, parks) are only acceptable if they have substantial permanent indoor space."
        )
    elif _bad_weather:
        weather_rule = (
            f"4. WEATHER ALERT: {weather_report}. Avoid recommending outdoor-only venues "
            "(beer gardens, rooftop bars, outdoor patios, parks) unless they have substantial indoor space. "
            "Prioritize covered or indoor venues."
        )
    else:
        weather_rule = f"4. WEATHER: {weather_report}. No weather restrictions."

    _group = filters_dict.get('group', '')
    if _group == "Friends":
        group_rule = (
            "GROUP RULE: This is a group of FRIENDS. "
            "NEVER recommend intimate, romantic, or date-focused venues (quiet wine bars for two, candlelit dinners, etc.). "
            "Prioritize lively, social, group-friendly spots with energy and a fun atmosphere."
        )
    elif _group == "Date":
        group_rule = (
            "GROUP RULE: This is a DATE. "
            "NEVER recommend loud sports bars, group party venues, or high-energy crowd spots. "
            "Prioritize intimate, impressive, conversation-friendly venues."
        )
    elif _group == "Family Outing":
        group_rule = (
            "GROUP RULE: This is a FAMILY OUTING. "
            "NEVER recommend breweries, bars, cocktail lounges, taprooms, nightclubs, or any alcohol-focused venue — "
            "children cannot enter many of these. "
            "Prioritize: museums, parks, family entertainment venues, restaurants with kids menus, outdoor activities. "
            "Any venue whose primary purpose is alcohol service is FORBIDDEN for this group."
        )
    elif _group == "Solo":
        group_rule = (
            "GROUP RULE: This is a SOLO outing. "
            "Prioritize places comfortable for one person — bars with good atmosphere, museums, "
            "coffee shops, solo-friendly dining. Avoid venues that feel awkward alone."
        )
    else:
        group_rule = ""

    _spend = filters_dict.get('spend', '💰 Moderate')
    if _spend == "🆓 Free":
        free_absolute_rule = (
            "ABSOLUTE RULE — FREE BUDGET: The user has selected FREE. This means ZERO cost to enter or participate. "
            "You must ONLY recommend: public parks, trails, nature areas, free museums (Smithsonian, public galleries), "
            "free community events, free outdoor spaces (waterfronts, plazas, botanical gardens that are free), "
            "window shopping areas, free markets. "
            "NEVER recommend: breweries, bars, restaurants, paid attractions, escape rooms, bowling, "
            "or ANY venue that charges money. "
            "If the Places data contains no free venues, say so explicitly and recommend the best free public spaces in the area instead."
        )
        budget_rule = ""
    else:
        free_absolute_rule = ""
        if _spend == "✨ Splurge":
            budget_rule = (
                "BUDGET RULE: User is splurging. Prioritize upscale, impressive, high-end experiences. "
                "Avoid casual or budget spots."
            )
        else:
            budget_rule = ""

    price_rule = (
        "PRICE PREFERENCE: Each venue includes a priceLevel field. "
        f"The user's spend filter is '{_spend}'. "
        "Cross-reference: PRICE_LEVEL_FREE→🆓 Free, PRICE_LEVEL_INEXPENSIVE/MODERATE→💰 Moderate, "
        "PRICE_LEVEL_EXPENSIVE/VERY_EXPENSIVE→✨ Splurge. "
        "Strongly prefer venues whose priceLevel matches the filter. "
        "If insufficient price-matched venues exist in the data, use the best available options "
        "and note the approximate price in why_its_perfect."
    )

    _intended_time = filters_dict.get('time', 'this evening')
    hours_rule = (
        f"HOURS PREFERENCE: Prefer venues that are open at the user's intended time ({_intended_time}). "
        "If currentOpeningHours shows a venue is definitively closed, prefer alternatives when they exist. "
        "If hours data is unavailable or ambiguous, include the venue — assume it may be open. "
        "If no clearly-open venues remain after other constraints, use the best available options regardless of hours."
    )

    hidden_gem_mandate = (
        "HIDDEN GEM MANDATE: For the TIER 3 (Hidden Gem) recommendation specifically, actively prefer:\n"
        "- Venues with fewer than 100 Google reviews (newer = better)\n"
        "- Venues whose name or description contains: pop-up, grand opening, soft launch, new, just opened, hidden, speakeasy, secret, limited time\n"
        "- Non-traditional experiences: escape rooms, art studios, pottery, maker spaces, hiking trails, scenic viewpoints, community galleries\n"
        "- Results tagged freshness_boost=True in TIER 3 DATA are newly discovered — strongly prefer these\n"
        "- Avoid recommending well-known chains or tourist spots for this tier — if it has 500+ reviews it is NOT a hidden gem"
    )

    specific_rule = ""
    if filters_dict.get('specific'):
        _spec = filters_dict['specific']
        specific_rule = f"""14. MANDATORY OVERRIDE — SPECIFIC REQUEST: '{_spec}'
    This is NON-NEGOTIABLE. ALL 3 recommendations MUST directly relate to '{_spec}'.
    If the Google Places data doesn't have enough relevant results, use the closest matches available
    and explain the connection in why_its_perfect.
    The matched_tags array MUST contain the exact keyword '{_spec}'.
    - "happy hour" → bars/restaurants with happy hour specials; mention deals/times in why_its_perfect
    - "live music" → confirmed live music venues only
    - "romantic" → intimate, quiet, date-appropriate only
    Do NOT return results that ignore this keyword."""

    # Geography rule
    geo_center = f"{location_name}{f' (lat={lat:.4f}, lng={lng:.4f})' if lat and lng else ''}"
    geo_rule = (
        f"1. STRICT GEOGRAPHY: Search center is {geo_center}. "
        f"Every result MUST be within {radius_miles} miles. "
        "For events specifically: the venue must be in the search city or its immediate suburbs — NOT a distant city. "
        "OUT-OF-RANGE examples for a Northern VA/DC search: Virginia Beach, Richmond, Ocean City, Baltimore. "
        "If an event venue city does not match the search location or its suburbs, discard it and use a Google Places result."
    )

    # Events rule — hierarchy depends on food filter
    food_filter = filters_dict.get('food', '')
    if food_filter == "Full Meal":
        events_rule = (
            "2. DATA SOURCE — FULL MEAL MODE: Google Places is your ONLY source. "
            "The user wants restaurants and dining. DO NOT use any live events regardless of verification. "
            "Ignore the events section entirely. All 3 results must be restaurants/dining from Google Places."
        )
    elif food_filter == "Just Drinks/Coffee":
        events_rule = (
            "2. DATA SOURCE PRIORITY: Google Places is PRIMARY (use for at least 2 of 3 results). "
            "One event slot is acceptable ONLY if ALL of these are true: "
            "(a) date_verified=True on today's date, "
            "(b) the event venue is within the search radius in the correct city/suburbs, "
            "(c) the event is drinks or nightlife related. "
            "If no event meets all three criteria, use Google Places for all results."
        )
    else:  # No Food Needed
        events_rule = (
            "2. DATA SOURCE PRIORITY: Google Places is PRIMARY — default to it for all results. "
            "Events may fill ONE slot only if ALL of these are true: "
            "(a) date_verified=True on today's date, "
            "(b) venue is physically inside the search city or immediate suburbs within the radius. "
            "If any doubt about an event's location or date, skip it and use a Google Places result."
        )

    system_prompt = f"""You are a local concierge for 'Get Wild'.

CONTEXT: {location_name} | {weather_report} | {target_date_str} ({relative_day}) | {filters_dict['time']} | {filters_dict['group']}, {filters_dict['food']}, {filters_dict['vibe']}
{profile_context}{taste_context}
{blacklist_context}
RULES:
{f"0. {free_absolute_rule}" + chr(10) if free_absolute_rule else ""}{geo_rule}
{events_rule}
3. EVENTS DATE CHECK: Only events with date_verified=True on {relative_day} ({target_date_str}) are eligible. why_its_perfect must include venue name and address. Never fabricate event details.
{weather_rule}
5. NO HALLUCINATION: Use exact addresses and URLs from input data. Never invent.
6. VARIETY PREFERENCE: Strongly prefer recommendations from different venue categories when the data allows. Specifically:
   - Avoid two venues from the exact same subcategory (two identical bar types, two of the same cuisine) when alternatives exist in the data
   - If food filter is 'No Food Needed' or 'Just Drinks/Coffee', try to include at least one non-food venue
   - Avoid returning 3 events — Google Places should provide most results
   - If the available data genuinely has limited variety, it is acceptable to use the same category — returning 3 results is always more important than strict variety
{f"7. {group_rule}" if group_rule else ""}
{f"8. {budget_rule}" if budget_rule else ""}
9. {price_rule}
10. {hours_rule}
11. {hidden_gem_mandate}
12. FRESHNESS BONUS: Any venue tagged just_opened=True in the input data is a priority pick for the TIER 3 (Hidden Gem) or TIER 2 (Fresh Take) recommendation — these are rare finds. Always include one if available.
13. TRAIL DATA: Some results may be tagged source=alltrails. These are real verified trails with difficulty ratings and length. For outdoor/active searches, strongly consider including one trail as the Adventure or Hidden Gem tier pick.
{specific_rule}

{instruction}

FALLBACK: If strict rules leave fewer than 3 valid options, relax non-critical preferences (variety, price matching, hours) to ensure exactly 3 recommendations are always returned. It is always better to return 3 slightly imperfect results than 1 perfect result. Never return fewer than 3.

Return JSON with a 'recommendations' array. Each item: name, tier_name, category, address (exact), why_its_perfect (2-3 sentences), vibe_check (3 words), matched_tags (2-3 strings; mandatory if specific given), website, lat, lng, spontaneity_score (integer 1-10 using this strict rubric — DO NOT inflate scores: 1-2=mainstream chain or famous landmark everyone knows (Smithsonian, Cheesecake Factory, Central Park); 3-4=solid local spot most people have heard of or would immediately think to Google (neighborhood brewery, popular brunch spot, well-known hiking trail); 5-6=genuinely interesting find that most people wouldn't think of themselves but is easy to enjoy (rooftop bar with no reservations needed, lesser-known gallery, unique food hall); 7-8=surprisingly unconventional or hard-to-discover — requires insider knowledge or creative thinking (hidden speakeasy, axe throwing bar, ceramics class, underground supper club); 9-10=truly rare, unexpected, or brand-new — most locals haven't heard of it yet (pop-up experience, brand-new venue in soft opening, extremely niche activity). A small local museum scores 3-4. A neighborhood park scores 2-3. A bowling alley scores 5. Axe throwing scores 7. A brand-new pop-up art installation scores 9.)"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    (
                        f"=== TIER 1 DATA (Crowd-Pleasing — highly rated, established) ===\n{json.dumps(trimmed_t1)}\n\n"
                        f"=== TIER 2 DATA (Fresh Take — new, trending, interesting) ===\n{json.dumps(trimmed_t2)}\n\n"
                        f"=== TIER 3 DATA (Hidden Gem — quirky, unconventional, lesser-known) ===\n{json.dumps(trimmed_t3)}\n\n"
                    ) if _is_tiered else (
                        f"=== PRIMARY DATA (Google Places) ===\n{json.dumps(trimmed_places)}\n\n"
                    )
                ) + (
                    f"=== EVENTS DATA (max 1 slot, only if food filter allows) ===\n"
                    f"{json.dumps(safe_events_data) if isinstance(safe_events_data, list) else safe_events_data}"
                )}
            ],
            max_tokens=2500,
            timeout=30
        )
    except Exception as e:
        if "timeout" in type(e).__name__.lower() or "timeout" in str(e).lower():
            raise TimeoutError("Taking longer than usual, please try again")
        raise
    
    raw_content = response.choices[0].message.content.strip()
    if raw_content.startswith("```json"):
        raw_content = raw_content[7:-3].strip()
    elif raw_content.startswith("```"):
        raw_content = raw_content[3:-3].strip()
        
    return json.loads(raw_content)

def match_photos_to_results(recommendations, raw_places, live_events=None, places_photo_map=None):
    # Build event image lookup keyed by normalised title AND venue_name
    # (AI sometimes uses the venue name rather than the event title)
    event_images = {}
    for ev in (live_events or []):
        img = ev.get('image_url')
        if not img:
            continue
        title = ev.get('title', '').lower().replace(' ', '')
        venue = ev.get('venue_name', '').lower().replace(' ', '')
        if title:
            event_images[title] = img
        if venue:
            event_images.setdefault(venue, img)  # title takes priority if both match

    # Build Places photo lookup — use pre-built map if provided (no HEAD requests needed),
    # otherwise build from raw_places with HEAD validation as fallback
    if places_photo_map is not None:
        place_photos = {k.lower().replace(' ', ''): v for k, v in places_photo_map.items() if v}
    else:
        place_photos = {}
        for place in (raw_places or []):
            name = place.get('displayName', {}).get('text', '').lower().replace(' ', '')
            if name and place.get('photo_url'):
                url = place['photo_url']
                try:
                    r = requests.head(url, timeout=3)
                    if r.status_code == 200:
                        place_photos[name] = url
                except:
                    pass

    for rec in recommendations:
        rec_name = rec.get('name', '').lower().replace(' ', '')

        # 1. Exact event title / venue_name match
        if rec_name in event_images:
            rec['photo_url'] = event_images[rec_name]
            continue

        # 2. Partial event match (substring either direction)
        ev_matched = False
        for ev_key, ev_img in event_images.items():
            if ev_key in rec_name or rec_name in ev_key:
                rec['photo_url'] = ev_img
                ev_matched = True
                break
        if ev_matched:
            continue

        # 3. Exact Places match
        if rec_name in place_photos:
            rec['photo_url'] = place_photos[rec_name]
            continue

        # 4. Partial Places match (substring either direction)
        matched = False
        for place_key, url in place_photos.items():
            if place_key in rec_name or rec_name in place_key:
                rec['photo_url'] = url
                matched = True
                break
        if not matched:
            rec['photo_url'] = None

    return recommendations

_UNSPLASH_FALLBACKS = {
    "wine":          "https://images.unsplash.com/photo-1510812431401-41d2bd2722f3?w=800&q=80",
    "brewery":       "https://images.unsplash.com/photo-1575367439058-6096bb9cf5e2?w=800&q=80",
    "bar":           "https://images.unsplash.com/photo-1575367439058-6096bb9cf5e2?w=800&q=80",
    "coffee":        "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=800&q=80",
    "music":         "https://images.unsplash.com/photo-1540039155732-d68a96670afb?w=800&q=80",
    "theater":       "https://images.unsplash.com/photo-1507676184212-d03ab07a01bf?w=800&q=80",
    "museum":        "https://images.unsplash.com/photo-1554907984-15263bfd63bd?w=800&q=80",
    "gallery":       "https://images.unsplash.com/photo-1554907984-15263bfd63bd?w=800&q=80",
    "park":          "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800&q=80",
    "trail":         "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800&q=80",
    "garden":        "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800&q=80",
    "restaurant":    "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&q=80",
    "entertainment": "https://images.unsplash.com/photo-1511882150382-421056c89033?w=800&q=80",
}
_CAT_RULES_IMG = [
    (["winery", "wine bar", "vineyard"],                          "wine"),
    (["brewery", "brewpub", "taproom", "craft beer"],             "brewery"),
    (["cocktail bar", "speakeasy", "lounge", "bar", "pub"],       "bar"),
    (["cafe", "coffee shop", "espresso", "tea house"],            "coffee"),
    (["concert hall", "music venue", "jazz club", "live music"],  "music"),
    (["theater", "comedy club", "cinema", "movie theater"],       "theater"),
    (["museum", "history museum", "science museum"],              "museum"),
    (["art gallery", "gallery"],                                   "gallery"),
    (["national park", "state park", "park", "botanical garden",
      "arboretum", "nature preserve", "hiking trail", "trail"],   "park"),
    (["restaurant", "bistro", "eatery", "diner", "kitchen"],      "restaurant"),
    (["escape room", "arcade", "bowling", "trampoline",
      "axe throwing", "entertainment"],                            "entertainment"),
]
_TEXT_RULES_IMG = [
    (["wine", "winery", "vineyard", "sommelier"],                 "wine"),
    (["brewery", "brewing", "brewpub", "craft beer", "taproom"],  "brewery"),
    (["cocktail", "speakeasy", "lounge", " bar", " pub"],         "bar"),
    (["coffee", "cafe", "espresso", "tea"],                       "coffee"),
    (["concert", "live music", "jazz", "band", "music venue"],    "music"),
    (["theater", "comedy", "cinema", "show"],                     "theater"),
    (["museum", "exhibit", "exhibition"],                          "museum"),
    (["art gallery", "gallery", "art space"],                     "gallery"),
    (["park", "garden", "nature", "trail", "hiking", "outdoor"],  "park"),
    (["restaurant", "dining", "food", "bistro", "kitchen"],       "restaurant"),
    (["bowling", "escape room", "arcade", "entertainment", "activity"], "entertainment"),
]

def get_fallback_image(category, text=""):
    """Return a category-appropriate Unsplash URL. Checks category string first, then text."""
    cat = (category or '').lower().strip()
    for keywords, bucket in _CAT_RULES_IMG:
        if any(k in cat for k in keywords):
            return _UNSPLASH_FALLBACKS[bucket]
    if text:
        t = text.lower()
        for keywords, bucket in _TEXT_RULES_IMG:
            if any(k in t for k in keywords):
                return _UNSPLASH_FALLBACKS[bucket]
    return "https://images.unsplash.com/photo-1514214246283-d427a95c5d2f?w=800&q=80"


def render_spot_card(spot, location_input, user_id, index, mode):
    title_prefix = f"{index}." if mode == "top_3" else "🎲"

    search_term = spot['name'].replace(' ', '+') + f"+{location_input.replace(' ', '+')}"
    map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
    encoded_address = urllib.parse.quote(spot['address'])
    uber_url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_address}"

    extra_text = " ".join([
        spot.get('tier_name', '') or '',
        spot.get('why_its_perfect', '') or '',
    ])
    fallback_url = get_fallback_image(spot.get('category', ''), extra_text)
    img_url = spot.get('photo_url') or fallback_url

    # Tag pills
    tags_html = ""
    matched_tags = spot.get('matched_tags')
    if matched_tags:
        if isinstance(matched_tags, str):
            matched_tags = [t.strip() for t in matched_tags.split(',') if t.strip()]
        for tag in matched_tags:
            tags_html += f'<span class="wc-tag">✓ {tag}</span>'

    tier_name  = spot.get('tier_name', 'Top Pick')
    category   = spot.get('category', '')
    vibe       = spot.get('vibe_check', '')
    address    = spot.get('address', '')
    pitch      = spot.get('why_its_perfect', '')
    start_time = spot.get('start_time', '')
    venue_name = spot.get('venue_name', '')

    # Tier badge left-border color by pool membership
    _tn = tier_name.lower()
    if _tn in {"the sure thing", "the crowd pleaser", "the local favorite", "the classic", "the reliable"}:
        _tier_color = "#52b788"
    elif _tn in {"the fresh take", "the curveball", "the surprise", "the interesting pick", "the plot twist"}:
        _tier_color = "#f4a261"
    elif _tn in {"the hidden gem", "the wild card", "the adventure", "the deep cut", "the discovery"}:
        _tier_color = "#e76f51"
    else:
        _tier_color = "#2d6a4f"  # get_wild / Spontaneous Adventure

    # Vibe check pills
    _vibe_words = [w.strip() for w in vibe.split(',') if w.strip()] if vibe else []
    if _vibe_words:
        _pills = [f'<span class="wc-vibe-pill">{"✨ " if i == 0 else ""}{w}</span>'
                  for i, w in enumerate(_vibe_words)]
        vibe_pills_html = '<div class="wc-vibe-row">' + ''.join(_pills) + '</div>'
    else:
        vibe_pills_html = ''

    # Event time line shown below venue name (Ticketmaster events only)
    _cat_lower = (category or '').lower()
    is_event = bool(spot.get('image_url')) or any(k in _cat_lower for k in [
        'event', 'music', 'sports', 'concert', 'arts', 'entertainment',
        'concert hall', 'performing arts', 'theater', 'arena', 'stadium',
    ])
    event_time_html = ''
    if is_event and start_time and start_time != 'Time TBD':
        time_line = f"🕐 {start_time}"
        if venue_name:
            time_line += f" · {venue_name}"
        event_time_html = f'<div class="wc-meta" style="margin-bottom:8px;">{time_line}</div>'

    # Utility row links — "Get Tickets" for events, "Website" for places
    share_text     = f"Let's go to {spot['name']}! {address}\n{map_url}"
    share_encoded  = urllib.parse.quote(share_text)
    share_subj_enc = urllib.parse.quote(f"Wild Plan: {spot['name']}")
    share_body_enc = urllib.parse.quote(share_text)
    sep = '<span class="wc-util-sep">|</span>'
    if spot.get('website'):
        link_label = '🎟️ Get Tickets' if is_event else '🌐 Website'
        website_part = f'<a href="{spot["website"]}" target="_blank" class="wc-util-link">{link_label}</a>{sep}'
    else:
        website_part = ''
    utility_html = (
        f'<div class="wc-utility">'
        f'{website_part}'
        f'<a href="{map_url}" target="_blank" class="wc-util-link">🗺️ Directions</a>{sep}'
        f'<a href="{uber_url}" target="_blank" class="wc-util-link">🚗 Uber</a>{sep}'
        f'<a href="sms:?body={share_encoded}" class="wc-util-link">📱 Text</a>{sep}'
        f'<a href="mailto:?subject={share_subj_enc}&body={share_body_enc}" class="wc-util-link">📧 Email</a>'
        f'</div>'
    )

    # GET WILD: inject anchor + green glow CSS targeting the native border wrapper
    if mode == "get_wild":
        st.markdown(
            '<style>'
            'div:has(#wca-wild)+[data-testid="stVerticalBlockBorderWrapper"]{'
            'border-color:#2d6a4f!important;'
            'box-shadow:0 0 20px rgba(45,106,79,0.4),0 0 40px rgba(45,106,79,0.2)!important;'
            'animation:wildGlow 3s ease-in-out infinite!important;'
            '}'
            '</style>'
            '<p style="color:#2d6a4f;font-weight:700;font-size:1.05rem;margin:8px 0 4px 0;">🎲 Your Wild Adventure Awaits</p>'
            '<div id="wca-wild"></div>',
            unsafe_allow_html=True
        )

    html_card = f"""<div class="wc-shell">
  <div class="wc-img-wrap">
    <img src="{img_url}" class="wc-img" alt="">
    <div class="wc-tier" style="border-left: 3px solid {_tier_color};">✦ {tier_name}</div>
  </div>
  <div class="wc-body">
    <div class="wc-name">{title_prefix} {spot['name']}</div>
    <div class="wc-meta">{category}</div>
    {vibe_pills_html}{event_time_html}<div class="wc-address">📍 {address}</div>
    {utility_html}
    <hr class="wc-hr">
    <p class="wc-pitch">{pitch}</p>
    <div class="wc-tags">{tags_html}</div>
  </div>
</div>
"""
    with st.container(border=True):
        st.markdown(html_card, unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        _ctx = dict(
            mode=mode,
            group_type=st.session_state.get('mem_group', ''),
            setting=st.session_state.get('mem_vibe', ''),
            spend=st.session_state.get('mem_spend', ''),
            tier_name=spot.get('tier_name', ''),
        )
        with col1:
            if st.button("⭐ Save", key=f"save_{index}_{spot['name']}", use_container_width=True, help="Save for later"):
                _pre = save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'), **_ctx)
                _pts = POINTS['first_save'] if _pre == 0 else POINTS['save']
                award_points(user_id, "save", _pts, "First spot saved! 🎉" if _pre == 0 else "Saved a spot")
                check_and_award_badges(user_id)
        with col2:
            if st.button("✅ I'm Going", key=f"going_{index}_{spot['name']}", use_container_width=True, type="primary", help="Mark as chosen"):
                save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'), notes="chosen", **_ctx)
                _gpts = POINTS['going_wild'] if mode == 'get_wild' else POINTS['going_top3']
                award_points(user_id, "going", _gpts, "Chose an outing")
                check_and_award_badges(user_id)
        with col3:
            if st.button("👎 Not for me", key=f"nope_{index}_{spot['name']}", use_container_width=True, help="Never suggest this again"):
                save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'),
                                rating=1, notes="Blacklisted via quick-button.", **_ctx)

def fetch_alltrails_trails(lat, lng, radius_miles, difficulty=None):
    """Fetch trails from AllTrails API. Returns [] if key not configured."""
    if not ALLTRAILS_API_KEY:
        return []
    try:
        params = {
            "key": ALLTRAILS_API_KEY,
            "lat": lat,
            "lon": lng,
            "radius": radius_miles,
            "limit": 5,
            "units": "i",  # imperial (miles)
        }
        if difficulty:
            params["difficulty"] = difficulty
        response = requests.get(
            "https://api.alltrails.com/api/v2/trails",
            params=params,
            timeout=8,
        )
        if response.status_code != 200:
            return []
        trails_raw = response.json().get("trails", response.json().get("data", []))
        results = []
        for t in trails_raw:
            results.append({
                "title":          t.get("name", ""),
                "name":           t.get("name", ""),
                "description":    t.get("description", ""),
                "difficulty":     t.get("difficulty", ""),
                "length_miles":   t.get("length") or t.get("length_miles"),
                "elevation_gain": t.get("elevation_gain"),
                "rating":         t.get("avg_rating") or t.get("rating"),
                "photo_url":      (t.get("profile_photo_data") or {}).get("medium_url") or t.get("photo_url"),
                "url":            t.get("url", ""),
                "lat":            t.get("lat") or t.get("latitude"),
                "lng":            t.get("lng") or t.get("longitude"),
                "source":         "alltrails",
                "category":       "Trail",
            })
        return results
    except:
        return []

# ==========================================
# 5. ASYNC DATA GATHERER
# ==========================================
_TRAIL_KEYWORDS = {"hike", "trail", "bike", "nature", "outdoor", "walk"}

async def gather_all_data(lat, lng, places_input, distance, target_date_str, user_id, specific_keyword="", vibe="", food="", mode=""):
    """places_input: tuple of (t1q, t2q, t3q) for tier-based fetching, or str for single semantic query."""
    async def _events_with_timeout():
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fetch_live_events, lat, lng, distance, target_date_str, specific_keyword),
                timeout=5.0
            )
        except (asyncio.TimeoutError, Exception):
            return []

    _want_trails = (
        (vibe == "Outside" and food == "No Food Needed") or
        any(kw in (specific_keyword or "").lower() for kw in _TRAIL_KEYWORDS)
    )

    async def _trails_task():
        if _want_trails:
            return await asyncio.to_thread(fetch_alltrails_trails, lat, lng, distance)
        return []

    weather_task  = asyncio.to_thread(get_live_weather, lat, lng)
    excluded_task = asyncio.to_thread(get_excluded_spots, user_id)
    favorites_task = asyncio.to_thread(get_favorite_spots, user_id)
    prefs_task    = asyncio.to_thread(get_user_preference_scores, user_id)
    if isinstance(places_input, tuple):
        places_task = asyncio.to_thread(fetch_tier_places, *places_input, lat, lng, distance)
    else:
        places_task = asyncio.to_thread(fetch_places_semantic, places_input, lat, lng, distance, vibe, food)
    return await asyncio.gather(weather_task, places_task, _events_with_timeout(), excluded_task, favorites_task, prefs_task, _trails_task())

# ==========================================
# 6. UI ROUTING
# ==========================================
_hero_col, _fb_col = st.columns([9, 1])
with _hero_col:
    st.markdown("""
<div class="hero-header">
    <h1 class="hero-title">Get Wild</h1>
    <p class="hero-subtitle">Disconnect. Explore. Connect.</p>
</div>
""", unsafe_allow_html=True)
with _fb_col:
    st.write("")  # vertical nudge to align with header
    _fb_user_id = st.session_state.user.id if st.session_state.get('user') else None
    with st.popover("💬", help="Send feedback"):
        st.markdown("**What's on your mind?**")
        st.caption("Bug, idea, or general feedback — we read everything.")
        st.text_area("", placeholder="Type here...", label_visibility="collapsed", key="fb_textarea")
        if st.button("Send Feedback", type="primary", use_container_width=True, key="fb_submit"):
            _fb_comment = st.session_state.get("fb_textarea", "")
            if not _fb_comment.strip():
                st.warning("Please write something before sending.")
            else:
                _fb_result = submit_feedback(_fb_user_id, _fb_comment)
                if _fb_result is True:
                    st.toast("✅ Feedback sent! Thank you.")
                else:
                    st.error(f"DB error: {_fb_result}")

if st.session_state.user is None:
    st.write("---")
    st.subheader("Welcome to the Wild.")
    
    tab_login, tab_signup = st.tabs(["Log In", "Sign Up"])
    with tab_login:
        with st.form("login_form"):
            email_login = st.text_input("Email")
            password_login = st.text_input("Password", type="password")
            if st.form_submit_button("Log In", type="primary", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email_login, "password": password_login})
                    st.session_state.user = res.user
                    generate_referral_code(res.user.id)
                    prof = get_profile(res.user.id)
                    if not prof or not prof.get('first_name'):
                        st.session_state.show_onboarding = True
                    st.rerun()
                except Exception as e: st.error("Login failed. Check your credentials.")

    with tab_signup:
        with st.form("signup_form"):
            email_signup = st.text_input("Email (New Account)")
            password_signup = st.text_input("Password (New Account)", type="password")
            if st.form_submit_button("Sign Up", type="primary", use_container_width=True):
                try:
                    res = supabase.auth.sign_up({"email": email_signup, "password": password_signup})
                    new_user = res.user
                    st.session_state.user = new_user
                    generate_referral_code(new_user.id)
                    # Process referral if the user arrived via an invite link
                    _ref = st.session_state.get('referral_code', '').strip()
                    if _ref:
                        try:
                            supabase.table('user_profiles').upsert(
                                {'id': new_user.id, 'referred_by': _ref}
                            ).execute()
                            supabase.rpc('award_referral_points', {
                                'p_referral_code': _ref,
                                'p_new_user_id': str(new_user.id),
                            }).execute()
                            award_points(new_user.id, 'signup_bonus', 5, 'Joined via friend invite')
                            st.session_state.show_welcome_bonus = True
                        except:
                            pass
                    st.session_state.show_onboarding = True
                    st.rerun()
                except Exception as e: st.error(f"Signup failed: {e}")

elif st.session_state.show_onboarding:
    st.markdown("## 🌿 Welcome to Get Wild!")
    st.subheader("Tell us about yourself for the best recommendations")
    st.write("This takes 60 seconds and makes every suggestion feel personal.")
    st.write("")

    with st.form("onboarding_form"):
        ob_name = st.text_input("Your first name *", placeholder="e.g. Alex")
        ob_group = st.selectbox("Who do you usually go out with?",
                                ["Just Me", "With a Partner", "With Friends", "With Family"])
        ob_alcohol = st.radio("Alcohol preference", ["Drinks Alcohol", "Non-Alcoholic Only"], horizontal=True)
        dietary_options = ["None", "Vegan", "Vegetarian", "Gluten-Free", "Nut Allergy", "Halal", "Kosher"]
        ob_dietary = st.multiselect("Any dietary needs?", dietary_options, default=["None"])
        ob_vibe = st.text_input("Describe your ideal vibe (optional)",
                                placeholder="e.g. cozy, lively, sophisticated, outdoorsy")
        ob_stroller = st.checkbox("Require Stroller Accessible venues")
        ob_dog = st.checkbox("Prefer Dog-Friendly venues")

        submitted = st.form_submit_button("Let's Get Wild 🌿", type="primary", use_container_width=True)
        if submitted:
            if not ob_name.strip():
                st.error("Please enter your first name to continue.")
            else:
                dietary_clean = [d for d in ob_dietary if d != "None"]
                supabase.table('user_profiles').upsert({
                    'id': st.session_state.user.id,
                    'first_name': ob_name.strip(),
                    'needs_stroller_access': ob_stroller,
                    'needs_dog_friendly': ob_dog,
                    'vibe_preference': ob_vibe.strip(),
                    'needs_nonalcoholic': ob_alcohol == "Non-Alcoholic Only",
                    'dietary_restrictions': ', '.join(dietary_clean),
                }).execute()
                st.session_state.show_onboarding = False
                st.rerun()

    if st.button("Skip for now →", type="secondary"):
        st.session_state.show_onboarding = False
        st.rerun()

else:
    if st.session_state.get('show_welcome_bonus'):
        st.success("🎉 Welcome bonus! You got 5 Wild Points for joining via invite!")
        st.session_state.show_welcome_bonus = False

    tab_explore, tab_profile, tab_saved = st.tabs(["🌍 Explore", "👤 My Profile", "⭐ Saved Spots"])

    with tab_explore:
        user_profile = get_profile(st.session_state.user.id)
        
        # --- SCREEN 1: THE INPUT FORM ---
        if not st.session_state.search_active:

            # ---- HERE'S A WILD IDEA BANNER ----
            if _should_show_wild_idea_teaser():
                _has_location = st.session_state.get('mem_gps_active') or bool(st.session_state.get('mem_loc', ''))

                if not _has_location:
                    # Greyed out — no location yet
                    st.markdown(
                        '<div style="background:#e5e7eb;color:#9ca3af;border-radius:24px;padding:10px 20px;'
                        'text-align:center;font-size:0.9rem;font-weight:600;margin-bottom:10px;user-select:none;">'
                        '💡 Search somewhere to unlock your Wild Idea →</div>',
                        unsafe_allow_html=True)

                elif not st.session_state.get('wild_idea_expanded'):
                    # Collapsed green teaser — pulsing pill button
                    st.markdown("""<style>
@keyframes wi-pulse{0%,100%{opacity:1}50%{opacity:0.78}}
.wi-teaser-anchor+div .stButton>button{
    background:linear-gradient(90deg,#2d6a4f,#52b788)!important;
    color:white!important;border:none!important;border-radius:24px!important;
    font-weight:700!important;font-size:0.94rem!important;letter-spacing:0.02em!important;
    animation:wi-pulse 2.5s ease-in-out infinite!important;
    padding:11px 20px!important;
}
.wi-teaser-anchor+div .stButton>button:hover{
    background:linear-gradient(90deg,#1b4332,#40916c)!important;opacity:1!important;
}
</style><div class="wi-teaser-anchor"></div>""", unsafe_allow_html=True)
                    if st.button("💡 Here's a Wild Idea — tap to reveal →",
                                 use_container_width=True, key="wi_teaser_reveal"):
                        st.session_state.wild_idea_expanded = True
                        st.rerun()

                else:
                    # Expanded — resolve location, generate idea, render full card
                    _wi_lat, _wi_lng, _wi_loc = None, None, ""
                    if st.session_state.mem_gps_active and st.session_state.mem_geo_data:
                        _wi_lat = st.session_state.mem_geo_data['latitude']
                        _wi_lng = st.session_state.mem_geo_data['longitude']
                        _wi_loc = "your current location"
                    elif st.session_state.mem_loc:
                        _wi_lat, _wi_lng = get_coordinates(st.session_state.mem_loc)
                        _wi_loc = st.session_state.mem_loc

                    if _wi_lat:
                        _prof_parts = []
                        if user_profile:
                            if user_profile.get('vibe_preference'): _prof_parts.append(user_profile['vibe_preference'])
                            if user_profile.get('needs_nonalcoholic'): _prof_parts.append("non-alcoholic")
                            if user_profile.get('dietary_restrictions'): _prof_parts.append(user_profile['dietary_restrictions'])
                        _prof_summary = ", ".join(_prof_parts) if _prof_parts else "no specific preferences"

                        _wi_pref_scores = get_user_preference_scores(st.session_state.user.id)
                        _wi_kws = tuple((_wi_pref_scores.get('top_keywords') or [])[:2]) if _wi_pref_scores else None

                        _idea = get_wild_idea(
                            str(st.session_state.user.id), _wi_lat, _wi_lng, _wi_loc, _prof_summary,
                            pref_keywords=_wi_kws,
                            radius_miles=st.session_state.get('mem_dist', 20),
                        )
                        if _idea:
                            st.markdown(
                                '<div style="font-size:0.72rem;font-weight:700;letter-spacing:1.2px;'
                                'color:#2d6a4f;margin-bottom:6px;">💡 HERE\'S A WILD IDEA...</div>',
                                unsafe_allow_html=True,
                            )
                            render_wild_idea_card(_idea, _wi_loc, st.session_state.user.id)
                        else:
                            # Generation failed — collapse to teaser
                            st.session_state.wild_idea_expanded = False
                    else:
                        # Location resolve failed — collapse
                        st.session_state.wild_idea_expanded = False
            # ---- END WILD IDEA BANNER ----

            st.subheader("Where are we going?")
            loc_col1, loc_col2 = st.columns([5, 1])
            
            with loc_col1: 
                ui_loc = st.text_input("Location", value=st.session_state.mem_loc, placeholder="Enter City or ZIP Code", label_visibility="collapsed")
            with loc_col2: 
                geo_data = streamlit_geolocation()

            if geo_data and geo_data.get('latitude') is not None:
                st.session_state.mem_gps_active = True
                st.session_state.mem_geo_data = geo_data
                st.session_state.mem_loc = "" 

            if st.session_state.mem_gps_active:
                st.success("🌿 GPS Locked!")

            st.write("---")
            st.subheader("What's the plan?")

            # Option mappings: display ↔ internal value
            _GROUP_OPTS  = ["💑 Date", "👨‍👩‍👧 Family", "👯 Friends", "🙋 Solo"]
            _GROUP_TO_INT = {"💑 Date": "Date", "👨‍👩‍👧 Family": "Family Outing", "👯 Friends": "Friends", "🙋 Solo": "Solo"}
            _INT_TO_GROUP = {v: k for k, v in _GROUP_TO_INT.items()}
            _VIBE_OPTS   = ["✨ Anywhere", "🌿 Outside", "🏠 Inside"]
            _VIBE_TO_INT  = {"✨ Anywhere": "Doesn't Matter", "🌿 Outside": "Outside", "🏠 Inside": "Inside"}
            _INT_TO_VIBE  = {v: k for k, v in _VIBE_TO_INT.items()}
            _FOOD_OPTS   = ["🍽️ Full Meal", "🍷 Drinks", "🎯 No Food"]
            _FOOD_TO_INT  = {"🍽️ Full Meal": "Full Meal", "🍷 Drinks": "Just Drinks/Coffee", "🎯 No Food": "No Food Needed"}
            _INT_TO_FOOD  = {v: k for k, v in _FOOD_TO_INT.items()}
            _SPEND_OPTS  = ["🆓 Free", "💰 Moderate", "✨ Splurge"]

            def _seg(label, options, default, sc_key):
                """Segmented control with radio fallback; syncs default on first render."""
                if sc_key not in st.session_state or st.session_state[sc_key] not in options:
                    st.session_state[sc_key] = default if default in options else options[0]
                try:
                    val = st.segmented_control(label, options, key=sc_key)
                    return val if val is not None else st.session_state[sc_key]
                except AttributeError:
                    idx = options.index(st.session_state[sc_key])
                    return st.radio(label, options, index=idx, horizontal=True, key=sc_key + "_r")

            # Row 1: Day + Time side by side
            _c1, _c2 = st.columns(2)
            with _c1:
                ui_day = _seg("📅 When?", ["☀️ Today", "📅 Tomorrow"], st.session_state.mem_day, "seg_day")
            with _c2:
                ui_time = _seg("🕐 Time?", ["☀️ Daytime", "🌙 Night"], st.session_state.mem_time, "seg_time")
            intended_time = f"{ui_day} ({ui_time})"

            # Row 2: Who
            ui_group_d = _seg("👥 Who?", _GROUP_OPTS, _INT_TO_GROUP.get(st.session_state.mem_group, "💑 Date"), "seg_group")
            ui_group   = _GROUP_TO_INT.get(ui_group_d, "Date")

            # Row 3: Setting
            ui_vibe_d = _seg("🌍 Setting?", _VIBE_OPTS, _INT_TO_VIBE.get(st.session_state.mem_vibe, "✨ Anywhere"), "seg_vibe")
            ui_vibe   = _VIBE_TO_INT.get(ui_vibe_d, "Doesn't Matter")

            # Row 4: Food
            ui_food_d = _seg("🍽️ Food?", _FOOD_OPTS, _INT_TO_FOOD.get(st.session_state.mem_food, "🍽️ Full Meal"), "seg_food")
            ui_food   = _FOOD_TO_INT.get(ui_food_d, "Full Meal")

            # Row 5: Budget
            ui_spend = _seg("💸 Budget?", _SPEND_OPTS, st.session_state.mem_spend, "seg_spend")

            # Row 6: Distance
            ui_dist = st.slider("📍 Max Distance (Miles)", 1, 20, st.session_state.mem_dist)

            # Row 7: Specific keyword (optional)
            with st.expander("🔍 Specific keyword? (Optional)", expanded=False):
                ui_spec = st.text_input("Keyword", value=st.session_state.mem_spec, placeholder="e.g., 'romantic', 'live jazz', 'axe throwing'", label_visibility="collapsed")

            st.write("---")
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1: top_3_clicked = st.button("🌟 Top 3 Recommendations", use_container_width=True)
            with btn_col2: get_wild_clicked = st.button("🎲 GET WILD", type="primary", use_container_width=True)

            wild_count = get_wild_count_today()
            if wild_count is not None and wild_count > 0:
                st.markdown(f"<div style='text-align:center;color:#e65100;font-weight:600;font-size:0.9rem;margin-top:4px;'>🔥 {wild_count} {'person' if wild_count == 1 else 'people'} got wild today — join them</div>", unsafe_allow_html=True)

            if top_3_clicked or get_wild_clicked:
                if not ui_loc and not st.session_state.mem_gps_active:
                    st.warning("Please enter a location or click the GPS icon first!")
                else:
                    st.session_state.mem_loc = ui_loc
                    st.session_state.mem_day = ui_day
                    st.session_state.mem_time = ui_time
                    st.session_state.mem_group = ui_group
                    st.session_state.mem_vibe = ui_vibe
                    st.session_state.mem_food = ui_food
                    st.session_state.mem_dist = ui_dist
                    st.session_state.mem_spec = ui_spec
                    st.session_state.mem_spend = ui_spend

                    st.session_state.current_mode = "get_wild" if get_wild_clicked else "top_3"
                    st.session_state.filters_dict = {
                        "group": ui_group, "time": intended_time,
                        "vibe": ui_vibe, "food": ui_food,
                        "specific": ui_spec, "spend": ui_spend
                    }
                    st.session_state.search_active = True
                    st.session_state.trigger_fetch = True
                    st.session_state.session_seen_spots = []
                    city = "Nearby" if st.session_state.mem_gps_active else (ui_loc.split()[0].rstrip(',') if ui_loc else "Unknown")
                    if get_wild_clicked:
                        increment_wild_counter(city)
                    st.rerun()

        # --- SCREEN 2: THE RESULTS & LOADER ---
        else:
            scroll_to_top()
            
            if st.button("← Start a Fresh Search"):
                st.session_state.search_active = False
                st.session_state.current_results = None
                st.session_state.session_seen_spots = []
                st.rerun()
                
            if st.session_state.trigger_fetch:
                st.session_state.trigger_fetch = False
                st.session_state.fetch_timed_out = False

                status_loader = st.empty()
                status_loader.info("📍 Locking in coordinates...")
                
                try:
                    location_context = st.session_state.mem_loc

                    if st.session_state.mem_gps_active and st.session_state.mem_geo_data:
                        lat, lng = st.session_state.mem_geo_data['latitude'], st.session_state.mem_geo_data['longitude']
                        location_context = "exact GPS coordinates"
                    else:
                        lat, lng = get_coordinates(st.session_state.mem_loc)

                    if lat is None:
                        status_loader.error("Couldn't find that location.")
                    else:
                        target_date_str, relative_day = get_local_target_date(lat, lng, st.session_state.mem_day)
                        pref_scores_pre = get_user_preference_scores(st.session_state.user.id)
                        # get_wild uses a single semantic query; top_3 uses 3 parallel tier queries
                        _is_get_wild = (st.session_state.current_mode == "get_wild")
                        if _is_get_wild or st.session_state.filters_dict.get('specific', '').strip():
                            places_input = build_semantic_query(st.session_state.filters_dict, user_profile, pref_scores_pre, mode=st.session_state.current_mode)
                        else:
                            places_input = build_tier_queries(st.session_state.filters_dict, user_profile, pref_scores_pre)

                        status_loader.info("☁️ Curating local weather, places, and events...")
                        def _run_gather():
                            return gather_all_data(
                                lat, lng, places_input, st.session_state.mem_dist,
                                target_date_str, st.session_state.user.id,
                                specific_keyword=st.session_state.filters_dict.get('specific', ''),
                                vibe=st.session_state.filters_dict.get('vibe', ''),
                                food=st.session_state.filters_dict.get('food', ''),
                                mode=st.session_state.current_mode,
                            )
                        try:
                            weather_report, raw_places, live_events_data, db_excluded, user_favorites, pref_scores, trail_results = asyncio.run(_run_gather())
                        except RuntimeError:
                            import nest_asyncio
                            nest_asyncio.apply()
                            weather_report, raw_places, live_events_data, db_excluded, user_favorites, pref_scores, trail_results = asyncio.run(_run_gather())
                        # Merge trail results — add to tier1 if tiered, else append to flat list
                        if trail_results:
                            if isinstance(raw_places, dict):
                                raw_places['tier1'] = (raw_places.get('tier1') or []) + trail_results
                            else:
                                raw_places = (raw_places or []) + trail_results

                        if st.session_state.current_mode == "get_wild":
                            status_loader.info("🎲 Loading up your adventure and revealing the spontaneity...")
                        else:
                            status_loader.info("🗺️ Assembling your perfect itinerary...")

                        all_excluded = list(set((db_excluded or []) + st.session_state.session_seen_spots))
                        user_favorites = user_favorites or []

                        cache_key = generate_cache_key(
                            st.session_state.filters_dict, location_context,
                            target_date_str, st.session_state.current_mode
                        )
                        cached_result = None
                        try:
                            cutoff = (datetime.utcnow() - timedelta(hours=2)).isoformat()
                            rows = supabase.table('recommendation_cache').select('result_json').eq('cache_key', cache_key).gte('created_at', cutoff).limit(1).execute()
                            if rows.data:
                                cached_result = json.loads(rows.data[0]['result_json'])
                        except:
                            pass

                        if cached_result and not st.session_state.get('skip_cache', False):
                            st.session_state.current_results = cached_result
                        else:
                            st.session_state.skip_cache = False
                            ai_results = get_ai_recommendations(
                                raw_places, live_events_data, weather_report,
                                st.session_state.filters_dict, location_context,
                                target_date_str, relative_day, user_profile, all_excluded,
                                user_favorites, mode=st.session_state.current_mode,
                                lat=lat, lng=lng, radius_miles=st.session_state.mem_dist,
                                preference_scores=pref_scores
                            )
                            # Build combined photo map from all tiers (or flat list for get_wild)
                            _all_places = []
                            if isinstance(raw_places, dict):
                                for _tier_list in raw_places.values():
                                    _all_places.extend(_tier_list)
                            else:
                                _all_places = raw_places or []
                            _places_photo_map = {
                                place.get('displayName', {}).get('text', '').lower().strip(): place.get('photo_url')
                                for place in _all_places
                                if place.get('photo_url')
                            }
                            match_photos_to_results(ai_results.get('recommendations', []), _all_places, live_events_data, _places_photo_map)

                            # Deduplicate by normalized venue name
                            import re as _re
                            def _norm_name(n):
                                n = (n or '').lower().strip()
                                n = _re.sub(r"^the\s+", "", n)
                                n = _re.sub(r"[^\w\s]", "", n)
                                return n.strip()
                            _seen_names, _deduped, _had_dupe = set(), [], False
                            for _rec in ai_results.get('recommendations', []):
                                _key = _norm_name(_rec.get('name', ''))
                                if _key not in _seen_names:
                                    _seen_names.add(_key)
                                    _deduped.append(_rec)
                                else:
                                    _had_dupe = True
                            ai_results['recommendations'] = _deduped
                            if _had_dupe:
                                st.warning("⚠️ Some duplicate venues were removed. Try 🔀 Shuffle for more variety.")

                            st.session_state.current_results = ai_results
                            try:
                                supabase.table('recommendation_cache').insert({
                                    'cache_key': cache_key,
                                    'result_json': json.dumps(st.session_state.current_results),
                                    'created_at': datetime.utcnow().isoformat()
                                }).execute()
                            except:
                                pass

                        for rec in st.session_state.current_results.get("recommendations", []):
                            st.session_state.session_seen_spots.append(rec['name'])

                        if st.session_state.current_mode == "get_wild":
                            status_loader.success("✅ Adventure Ready!")
                        else:
                            status_loader.success("✅ Itinerary Ready!")
                except Exception as e:
                    if isinstance(e, TimeoutError):
                        status_loader.error("Taking longer than usual, please try again.")
                        st.session_state.fetch_timed_out = True
                    else:
                        status_loader.error(f"Error connecting to the wild. Try again! ({type(e).__name__})")

            if st.session_state.fetch_timed_out:
                def _retry():
                    st.session_state.fetch_timed_out = False
                    st.session_state.trigger_fetch = True
                st.button("🔄 Try Again", on_click=_retry, type="primary", key="retry_timeout_btn")

            if st.session_state.current_results:
                st.write("---")
                results = st.session_state.current_results
                mode = st.session_state.current_mode
                
                # --- PYDECK INTERACTIVE MAP WITH HOVER TOOLTIPS ---
                map_data = []
                for i, spot in enumerate(results.get("recommendations", [])):
                    if spot.get('lat') and spot.get('lng'):
                        display_name = f"{i+1}. {spot['name']}" if mode == "top_3" else f"🎲 {spot['name']}"
                        spot_search = urllib.parse.quote(f"{spot['name']} {st.session_state.mem_loc}")
                        spot_map_url = f"https://www.google.com/maps/search/?api=1&query={spot_search}"
                        map_data.append({"lat": spot['lat'], "lon": spot['lng'], "name": display_name, "map_url": spot_map_url})
                
                if map_data:
                    with st.expander("🗺️ View on Map"):
                        layer = pdk.Layer(
                            'ScatterplotLayer',
                            data=map_data,
                            get_position='[lon, lat]',
                            get_color='[255, 75, 75, 200]',
                            get_radius=250,
                            pickable=True,
                        )
                        view_state = pdk.ViewState(latitude=map_data[0]['lat'], longitude=map_data[0]['lon'], zoom=12)
                        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip={"html": "<b>{name}</b>"}))
                        num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
                        map_btn_cols = st.columns(len(map_data))
                        for i, (col, item) in enumerate(zip(map_btn_cols, map_data)):
                            with col:
                                emoji = num_emojis[i] if i < len(num_emojis) else f"{i+1}."
                                st.link_button(f"{emoji} Open in Maps", item['map_url'], use_container_width=True)
                
                # --- RENDER CARDS ---
                for index, spot in enumerate(results.get("recommendations", [])):
                    render_spot_card(spot, st.session_state.mem_loc, st.session_state.user.id, index + 1, mode)
                    
                # --- SHUFFLE BUTTON (ONLY IN TOP 3 MODE) ---
                if mode == "top_3":
                    st.write("---")
                    if st.button("🔀 Shuffle", use_container_width=True):
                        st.session_state.trigger_fetch = True
                        st.session_state.skip_cache = True
                        st.rerun()

    # ----------------------------------------
    # TAB 2 & 3: PROFILE & SAVED SPOTS 
    # ----------------------------------------
    with tab_profile:
        current_prof = get_profile(st.session_state.user.id) or {}
        user_points  = get_user_points(st.session_state.user.id)

        st.markdown(f"## ⚡ {user_points} Wild Points")
        st.markdown(f"**🏆 Get Wild Tally: {current_prof.get('wild_tally', 0)}**")

        # Badges
        st.write("---")
        st.subheader("Your Badges")
        try:
            earned_badges = supabase.table('badges').select('*').eq('user_id', st.session_state.user.id).execute().data or []
        except:
            earned_badges = []

        if not earned_badges:
            st.info("No badges yet — get out there! 🌿")
        else:
            badge_cols = st.columns(min(len(earned_badges), 4))
            for i, b in enumerate(earned_badges):
                with badge_cols[i % 4]:
                    st.markdown(
                        f"<div style='text-align:center;font-size:2rem;line-height:1.2'>{b['badge_emoji']}</div>"
                        f"<div style='text-align:center;font-size:0.75rem;font-weight:600;margin-top:2px'>{b['badge_name']}</div>",
                        unsafe_allow_html=True
                    )

        with st.expander("How to earn points"):
            st.markdown("""
- **Save a spot** ⭐ → +1 pt
- **Choose an outing** (I'm Going) ✅ → +5 pts
- **Rate a visit 4-5 stars** → +1 pt
- **Invite a friend** 🌿 → +10 pts when they sign up
- **Join via invite** → +5 pts signup bonus
- **Explorer** 🧭 — First saved spot → +5 bonus pts
- **Trailblazer** 🥾 — 5 saves across different categories → +10 bonus pts
- **Wild at Heart** 💚 — 10 chosen outings → +25 bonus pts
- **Foodie** 🍽️ — 5 dining spots rated 4+ stars → +10 bonus pts
- **Night Owl** 🦉 — 3 bar/lounge/brewery spots saved → +10 bonus pts
- **Hidden Gem Hunter** 💎 — 5 Hidden Gem tier spots → +20 bonus pts
            """)

        st.write("---")
        st.subheader("🌿 Invite Friends")
        st.caption("Earn 10 points for every friend who joins Get Wild")
        _my_code = generate_referral_code(st.session_state.user.id)
        if _my_code:
            try:
                _base_url = st.query_params.get("_stcore_base_url", "https://get-wild.streamlit.app")
            except:
                _base_url = "https://get-wild.streamlit.app"
            _invite_link = f"{_base_url}?ref={_my_code}"
            st.text_input("Your invite link", value=_invite_link, disabled=True, label_visibility="collapsed")
            _msg = f"Hey! Check out Get Wild — it finds the best local spots and experiences. Use my link to join and we both get bonus points! {_invite_link}"
            import urllib.parse
            _sms_link = f"sms:?body={urllib.parse.quote(_msg)}"
            _email_link = f"mailto:?subject={urllib.parse.quote('Join me on Get Wild!')}&body={urllib.parse.quote(_msg)}"
            _ic1, _ic2 = st.columns(2)
            with _ic1:
                st.link_button("📱 Text a Friend", _sms_link, use_container_width=True)
            with _ic2:
                st.link_button("📧 Email a Friend", _email_link, use_container_width=True)
            try:
                _invited_count = supabase.rpc('get_referral_count', {'p_referral_code': _my_code}).execute().data or 0
            except:
                _invited_count = 0
            st.caption(f"👥 Friends invited: {_invited_count}")

        st.write("---")
        st.subheader("Personalize Your Profile")
        st.write("Set your baseline preferences so the app learns how you like to explore.")
        
        with st.form("profile_form"):
            fname = st.text_input("First Name", value=current_prof.get('first_name', ''))
            pname = st.text_input("Partner/Spouse Name (Optional)", value=current_prof.get('partner_name', ''))
            stroller = st.checkbox("Require Stroller Accessibility", value=current_prof.get('needs_stroller_access', False))
            dog = st.checkbox("Require Dog-Friendly Patios", value=current_prof.get('needs_dog_friendly', False))
            vibe_pref = st.text_area("What is your ideal aesthetic? (e.g., 'Warm, modern, naturalistic')", value=current_prof.get('vibe_preference', ''))
            alcohol_choice = st.radio("Alcohol Preference", ["Drinks Alcohol", "Non-Alcoholic Only"],
                index=1 if current_prof.get('needs_nonalcoholic', False) else 0)
            dietary_options = ["Vegan", "Vegetarian", "Gluten-Free", "Nut Allergy", "Halal", "Kosher"]
            current_dietary = [r.strip() for r in current_prof.get('dietary_restrictions', '').split(',') if r.strip()]
            dietary = st.multiselect("Dietary Restrictions", dietary_options, default=[d for d in current_dietary if d in dietary_options])

            if st.form_submit_button("Save Profile", type="primary"):
                supabase.table('user_profiles').upsert({
                    'id': st.session_state.user.id, 'first_name': fname, 'partner_name': pname,
                    'needs_stroller_access': stroller, 'needs_dog_friendly': dog, 'vibe_preference': vibe_pref,
                    'needs_nonalcoholic': alcohol_choice == "Non-Alcoholic Only",
                    'dietary_restrictions': ', '.join(dietary)
                }).execute()
                st.success("Your preferences have been locked in.")
                
        st.write("---")
        if st.button("🚪 Log Out", type="secondary"):
            supabase.auth.sign_out()
            st.session_state.user = None
            st.session_state.current_results = None
            st.session_state.session_seen_spots = []
            st.session_state.search_active = False
            st.session_state.trigger_fetch = False
            st.rerun()

    with tab_saved:
        st.subheader("Your Adventure Ledger")
        st.write("Rate your past spots. Spots rated 1-star will NEVER be recommended again.")
        # Always re-fetch fresh from Supabase — no caching
        st.session_state.saved_spots_dirty = False
        res = supabase.table('saved_spots').select('*').eq('user_id', st.session_state.user.id).order('saved_at', desc=True).execute()
        saved_spots = res.data if res.data else []

        if not saved_spots:
            st.info("You haven't saved any spots yet. Go explore!")
        else:
            # Rating nudge for spots marked "I'm Going" but not yet rated
            try:
                cutoff = (datetime.utcnow() - timedelta(hours=12)).isoformat()
                nudge_res = supabase.table('saved_spots').select('*')\
                    .eq('user_id', st.session_state.user.id)\
                    .eq('user_notes', 'chosen')\
                    .is_('rating', 'null')\
                    .lt('saved_at', cutoff)\
                    .execute()
                nudge_spots = nudge_res.data if nudge_res.data else []
            except:
                nudge_spots = []
            nudge_ids = {n['id'] for n in nudge_spots}

            for saved in saved_spots:
                if saved['id'] in nudge_ids:
                    st.markdown(
                        '<div style="border-left:4px solid #f4a261;border-radius:6px;padding:8px 12px;background:#fff8f0;margin-bottom:4px;">'
                        f'⭐ <b>How was your visit to {saved["spot_name"]}?</b> Tap to rate</div>',
                        unsafe_allow_html=True
                    )
                icon = "🚫" if saved['rating'] == 1 else "📍"
                with st.expander(f"{icon} {saved['spot_name']}"):
                    st.caption(saved['address'])

                    with st.form(f"rate_form_{saved['id']}"):
                        _star_opts = ["★", "★★", "★★★", "★★★★", "★★★★★"]
                        current_rating = saved['rating'] if saved['rating'] else 3
                        new_rating_stars = st.select_slider("Rate this spot (★ = Blacklist)", options=_star_opts, value=_star_opts[current_rating - 1])
                        new_rating = _star_opts.index(new_rating_stars) + 1
                        notes = st.text_input("Private Notes", value=saved.get('user_notes', ''))

                        if st.form_submit_button("Update Feedback", type="primary"):
                            supabase.table('saved_spots').update({'rating': new_rating, 'user_notes': notes}).eq('id', saved['id']).execute()
                            if new_rating == 5:
                                award_points(st.session_state.user.id, "rating", POINTS['rate'] + POINTS['rate_perfect'], "5-star rating!")
                            elif new_rating >= 4:
                                award_points(st.session_state.user.id, "rating", POINTS['rate'], "Rated a visit")
                            if new_rating >= 4:
                                check_and_award_badges(st.session_state.user.id)
                            st.success("Feedback saved!")
                            st.session_state.saved_spots_dirty = True
                            st.rerun()

                    if st.button("🗑️ Delete Spot", key=f"del_{saved['id']}"):
                        if delete_spot_from_db(saved['id']):
                            st.session_state.saved_spots_dirty = True
                            st.rerun()