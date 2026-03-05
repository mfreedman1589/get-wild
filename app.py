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
TIER_PERSONALITIES = [
    {"tier_name": "The Crowd-Pleaser",  "description": "A highly rated safe bet everyone will enjoy"},
    {"tier_name": "The Hidden Gem",     "description": "Quirky, unique, or off the beaten path"},
    {"tier_name": "The Fresh Take",     "description": "New, trending, or a live event happening now"},
    {"tier_name": "The Local Favorite", "description": "Where locals actually go, not tourists"},
    {"tier_name": "The Wild Card",      "description": "Unexpected and spontaneous — trust the process"},
    {"tier_name": "The Date Night Pick","description": "Intimate, romantic, and impressive"},
    {"tier_name": "The Comeback Kid",   "description": "An old classic that's been reinvented or is having a moment"},
    {"tier_name": "The Underdog",       "description": "Lesser known but punches above its weight"},
    {"tier_name": "The Vibe Match",     "description": "Perfectly matches the specific mood requested"},
    {"tier_name": "The Adventure",      "description": "Gets you out of your comfort zone"},
]

CACHE_VERSION = "v2"

BADGE_DEFINITIONS = [
    {"id": "explorer",      "name": "Explorer",          "emoji": "🧭", "pts": 5,
     "desc": "Save your first spot"},
    {"id": "trailblazer",   "name": "Trailblazer",       "emoji": "🥾", "pts": 10,
     "desc": "Save spots across 5 different categories"},
    {"id": "wild_at_heart", "name": "Wild at Heart",     "emoji": "💚", "pts": 25,
     "desc": "10 chosen outings"},
    {"id": "foodie",        "name": "Foodie",            "emoji": "🍽️", "pts": 10,
     "desc": "5 restaurant/dining spots rated 4+ stars"},
    {"id": "night_owl",     "name": "Night Owl",         "emoji": "🦉", "pts": 10,
     "desc": "Save 3 bar, lounge, or brewery spots"},
    {"id": "hidden_gem",    "name": "Hidden Gem Hunter", "emoji": "💎", "pts": 20,
     "desc": "Save 5 Hidden Gem tier spots"},
]

GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
TICKETMASTER_API_KEY = st.secrets["TICKETMASTER_API_KEY"]
OPENWEATHER_API_KEY = st.secrets["OPENWEATHER_API_KEY"] 
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

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
    .wc-tier { position: absolute; bottom: 10px; left: 12px; background: rgba(0,0,0,0.62); color: #fff; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.5px; padding: 4px 10px; border-radius: 20px; text-transform: uppercase; }

    .wc-body { padding: 16px; }
    .wc-name { font-size: 20px; font-weight: 700; color: #1a1a1a; margin: 0 0 5px 0; line-height: 1.3; }
    .wc-meta { font-size: 0.78rem; color: #888; margin-bottom: 3px; font-weight: 500; }
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
if 'mem_spend' not in st.session_state: st.session_state.mem_spend = "$ Moderate"
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

def save_spot_to_db(user_id, name, address, category, rating=None, notes=""):
    try:
        current_time = datetime.utcnow().isoformat()
        supabase.table('saved_spots').insert({
            'user_id': user_id, 
            'spot_name': name, 
            'address': address, 
            'category': category, 
            'rating': rating, 
            'user_notes': notes,
            'saved_at': current_time
        }).execute()
        
        if rating != 1:
            prof = get_profile(user_id)
            new_tally = (prof.get('wild_tally') or 0) + 1
            supabase.table('user_profiles').update({'wild_tally': new_tally}).eq('id', user_id).execute()
            st.toast(f"✅ Saved! Your Get Wild Tally is now {new_tally} 🏆")
        else:
            st.toast("🚫 Blacklisted. We won't recommend this again.")
    except Exception as e: st.error("Database error.")

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

def check_and_award_badges(user_id):
    try:
        spots = supabase.table('saved_spots').select('*').eq('user_id', user_id).execute().data or []
        earned = {b['badge_id'] for b in (supabase.table('badges').select('badge_id').eq('user_id', user_id).execute().data or [])}

        for badge in BADGE_DEFINITIONS:
            if badge['id'] in earned:
                continue
            bid = badge['id']
            unlocked = False

            if bid == 'explorer':
                unlocked = len(spots) >= 1
            elif bid == 'trailblazer':
                unlocked = len({s.get('category', '') for s in spots if s.get('category')}) >= 5
            elif bid == 'wild_at_heart':
                unlocked = len([s for s in spots if 'chosen' in (s.get('user_notes') or '') or (s.get('rating') or 0) > 0]) >= 10
            elif bid == 'foodie':
                unlocked = len([s for s in spots if any(k in (s.get('category') or '').lower() for k in ['restaurant', 'dining', 'food', 'bistro', 'kitchen']) and (s.get('rating') or 0) >= 4]) >= 5
            elif bid == 'night_owl':
                unlocked = len([s for s in spots if any(k in (s.get('category') or '').lower() for k in ['bar', 'lounge', 'brewery'])]) >= 3
            elif bid == 'hidden_gem':
                unlocked = len([s for s in spots if 'hidden gem' in (s.get('user_notes') or '').lower() or 'hidden gem' in (s.get('category') or '').lower()]) >= 5

            if unlocked:
                try:
                    supabase.table('badges').insert({
                        'user_id': user_id, 'badge_id': bid,
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

def build_semantic_query(filters_dict, profile, preference_scores=None):
    specific = (filters_dict.get('specific') or "").strip()
    vibe  = filters_dict.get('vibe', "Doesn't Matter")
    food  = filters_dict.get('food', 'Full Meal')
    group = filters_dict.get('group', '')
    spend = filters_dict.get('spend', '$ Moderate')

    # If specific keyword provided, it drives the query
    if specific:
        loc_hint = {"Date": "intimate", "Family Outing": "family-friendly", "Friends": "lively"}.get(group, "")
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

    # Base query by vibe + food + spend
    if vibe == "Outside":
        if is_free:
            base = "free parks hiking trails nature reserves free outdoor spaces scenic viewpoints"
        elif food == "Full Meal":
            base = "restaurants with nice patios"
        elif food == "Just Drinks/Coffee":
            base = "wineries, cocktail bars with patios, or upscale breweries"
        else:
            base = "parks, botanical gardens, hiking trails, scenic outdoor activities, nature reserves"
    elif vibe == "Inside":
        if is_free:
            base = "free museums free art galleries free community spaces free attractions"
        elif food == "Full Meal":
            base = "highly rated restaurants"
        elif food == "Just Drinks/Coffee":
            base = "wine bars, speakeasies, or lounges"
        else:
            base = "museums, art galleries, science centers, escape rooms, bowling alleys, entertainment venues, unique attractions"
    else:  # Doesn't Matter
        if is_free:
            base = "free activities free entertainment free museums free parks"
        elif food == "Full Meal":
            base = "highly rated restaurants"
        elif food == "Just Drinks/Coffee":
            base = "wine bars, speakeasies, or lounges"
        else:
            base = "museums, parks, entertainment venues, unique attractions, or outdoor experiences"

    # Spend-level suffix modifiers
    if is_free:
        modifiers.append("free admission no cover charge")
    elif spend == "$ Affordable":
        modifiers.append("affordable casual budget-friendly")
    elif spend == "$$ Splurge":
        if group == "Date":
            base = "michelin star fine dining tasting menu upscale cocktail lounge"
        else:
            modifiers.append("upscale fine dining luxury high-end rooftop")

    # Non-traditional venue extras for No Food / activity searches
    if no_food:
        if vibe == "Inside":
            modifiers.append("escape room pottery studio art class maker space community workshop")
        elif vibe == "Outside":
            modifiers.append("scenic viewpoint bike trail")
        modifiers.append("pop-up temporary installation")
    elif food != "Full Meal" and group in ("Date", "Friends"):
        modifiers.append("pottery studio art class cooking class")

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

def fetch_places_semantic(semantic_query, lat, lng, radius_miles):
    threshold = radius_miles * 1.5

    _JUST_OPENED_KWS = {"new", "just opened", "grand opening", "opening soon",
                        "soft launch", "pop-up", "popup", "newly opened"}

    def _process(places, freshness_boost=False):
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
            # Detect newly opened venues from name + editorial summary text
            _text = " ".join([
                (place.get('displayName', {}).get('text') or '').lower(),
                (place.get('editorialSummary', {}).get('text') or '').lower(),
            ])
            if any(kw in _text for kw in _JUST_OPENED_KWS):
                place['just_opened'] = True
            out.append(place)
        return out

    main_places   = _run_places_query(semantic_query, lat, lng, radius_miles, page_size=8)
    fresh_places  = _run_places_query(f"new opening pop-up unique hidden", lat, lng, radius_miles, page_size=3)

    seen_names = set()
    result = []
    for p in _process(main_places, freshness_boost=False):
        name = (p.get('displayName', {}).get('text') or '').lower()
        seen_names.add(name)
        result.append(p)
    for p in _process(fresh_places, freshness_boost=True):
        name = (p.get('displayName', {}).get('text') or '').lower()
        if name and name not in seen_names:
            seen_names.add(name)
            result.append(p)
    return result

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

def _should_show_wild_idea(user_profile):
    """All conditions must be true for the banner to render."""
    if st.session_state.get('wild_idea_dismissed'):
        return False
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
def get_wild_idea(user_id_str, lat, lng, location_name, profile_summary):
    """Returns a dict {name, category, why_now, emoji} or None. Cached 4 h."""
    try:
        # Use UTC hour as a reasonable time-of-day approximation
        h = datetime.utcnow().hour
        if 6 <= h < 12:
            time_context = "morning"
        elif 12 <= h < 17:
            time_context = "afternoon"
        elif 17 <= h < 21:
            time_context = "evening"
        else:
            time_context = "late night"

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": (
                f"You are a spontaneous local guide. Based on the time of day "
                f"({time_context}) and this user's preferences ({profile_summary}), "
                f"suggest ONE specific, surprising local activity or venue near "
                f"{location_name} (lat={lat:.3f}, lng={lng:.3f}). "
                "Be specific and exciting. "
                "Return JSON with exactly these keys: name, category, why_now "
                "(one punchy sentence, max 12 words), emoji."
            )}],
            max_tokens=120,
            timeout=10,
        )
        data = json.loads(response.choices[0].message.content.strip())
        # Validate required keys present
        if all(k in data for k in ("name", "category", "why_now", "emoji")):
            return data
    except:
        pass
    return None

# NOTE: Eventbrite supplemental events source was evaluated and skipped.
# Eventbrite's public event search API (GET /v3/events/search/ with lat/lng radius)
# was permanently removed on Feb 20, 2020. As of 2025 the API is effectively
# unsupported — no global search endpoint exists on any tier. Skip unless
# Eventbrite introduces a new discovery API.

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3), retry=retry_if_not_exception_type(TimeoutError))
def get_ai_recommendations(raw_places, live_events_data, weather_report, filters_dict, location_name, target_date_str, relative_day, profile, excluded_spots, favorite_spots, mode="top_3", tier_personalities=None, lat=None, lng=None, radius_miles=20, preference_scores=None):
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    trimmed_places = raw_places[:8] if isinstance(raw_places, list) and len(raw_places) > 8 else raw_places
    if isinstance(live_events_data, list):
        safe_events_data = live_events_data[:6]
    elif isinstance(live_events_data, str):
        safe_events_data = live_events_data[:4000]
    else:
        safe_events_data = live_events_data

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

    blacklist_context = f"CRITICAL: DO NOT RECOMMEND ANY OF THESE PLACES: {', '.join(excluded_spots)}" if excluded_spots else ""

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
        tiers = tier_personalities or TIER_PERSONALITIES[:3]
        tier_lines = "\n".join(f"        {i+1}. '{t['tier_name']}': {t['description']}." for i, t in enumerate(tiers))
        instruction = f"""
        Return EXACTLY 3 options from the data, providing STRICT VARIETY (do not return 3 of the exact same type of venue).
        Assign each to one of these directional 'tier_name' categories:
{tier_lines}
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
            "NEVER recommend bars, nightclubs, or adult-only venues. "
            "All results must be welcoming to children."
        )
    elif _group == "Solo":
        group_rule = (
            "GROUP RULE: This is a SOLO outing. "
            "Prioritize places comfortable for one person — bars with good atmosphere, museums, "
            "coffee shops, solo-friendly dining. Avoid venues that feel awkward alone."
        )
    else:
        group_rule = ""

    _spend = filters_dict.get('spend', '$ Moderate')
    if _spend == "🆓 Free":
        budget_rule = (
            "BUDGET RULE: User wants FREE options only. Every recommendation must be free or have no cover charge. "
            "No paid admission venues, no expensive restaurants."
        )
    elif _spend == "$$ Splurge":
        budget_rule = (
            "BUDGET RULE: User is splurging. Prioritize upscale, impressive, high-end experiences. "
            "Avoid casual or budget spots."
        )
    else:
        budget_rule = ""

    price_rule = (
        "PRICE MATCHING: Each venue in the Google Places data includes a priceLevel field. "
        f"The user's spend filter is '{_spend}'. "
        "Cross-reference priceLevel with the spend filter: "
        "PRICE_LEVEL_FREE→🆓 Free, PRICE_LEVEL_INEXPENSIVE→$ Affordable, "
        "PRICE_LEVEL_MODERATE→$ Moderate, PRICE_LEVEL_EXPENSIVE/VERY_EXPENSIVE→$$ Splurge. "
        "Strongly prefer venues whose priceLevel matches. "
        "NEVER recommend a PRICE_LEVEL_EXPENSIVE venue for a Free or Affordable search."
    )

    _intended_time = filters_dict.get('time', 'this evening')
    hours_rule = (
        f"HOURS RULE: If a venue's currentOpeningHours data shows it is CLOSED at the user's intended time ({_intended_time}), "
        "do NOT recommend it. Only recommend venues that are open or have no hours data available."
    )

    hidden_gem_mandate = (
        "HIDDEN GEM MANDATE: For the Hidden Gem tier specifically, actively prefer:\n"
        "- Venues with fewer than 100 Google reviews (newer = better)\n"
        "- Venues whose name or description contains: pop-up, grand opening, soft launch, new, just opened, hidden, speakeasy, secret, limited time\n"
        "- Non-traditional experiences: escape rooms, art studios, pottery, maker spaces, hiking trails, scenic viewpoints, community galleries\n"
        "- Results tagged freshness_boost=True in the input data are newly discovered — strongly prefer these for this tier\n"
        "- Avoid recommending well-known chains or tourist spots for this tier — if it has 500+ reviews it is NOT a hidden gem"
    )

    specific_rule = ""
    if filters_dict.get('specific'):
        _spec = filters_dict['specific']
        specific_rule = f"""13. MANDATORY OVERRIDE — SPECIFIC REQUEST: '{_spec}'
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
{geo_rule}
{events_rule}
3. EVENTS DATE CHECK: Only events with date_verified=True on {relative_day} ({target_date_str}) are eligible. why_its_perfect must include venue name and address. Never fabricate event details.
{weather_rule}
5. NO HALLUCINATION: Use exact addresses and URLs from input data. Never invent.
6. MANDATORY VARIETY RULE: The 3 recommendations MUST come from different venue categories. Specifically:
   - No two results can share the same primary category (e.g. two bars, two breweries, two restaurants of the same cuisine type)
   - At least one result should be non-food/drink focused if food filter is 'No Food Needed' or 'Just Drinks/Coffee'
   - If the Places data only contains one venue type, acknowledge this in why_its_perfect rather than returning 3 of the same thing
   - Never return 3 events; Google Places must provide the backbone of variety
{f"7. {group_rule}" if group_rule else ""}
{f"8. {budget_rule}" if budget_rule else ""}
9. {price_rule}
10. {hours_rule}
11. {hidden_gem_mandate}
12. FRESHNESS BONUS: Any venue tagged just_opened=True in the input data is a priority pick for the Hidden Gem or Fresh Take tier — these are rare finds. Always include one if available.
{specific_rule}

{instruction}

Return JSON with a 'recommendations' array. Each item: name, tier_name, category, address (exact), why_its_perfect (2-3 sentences), vibe_check (3 words), matched_tags (2-3 strings; mandatory if specific given), website, lat, lng, spontaneity_score (integer 1-10: 1-3=safe/predictable, 4-6=interesting but accessible, 7-10=genuinely unexpected/adventurous)."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"GOOGLE PLACES DATA: {json.dumps(trimmed_places)}\n\nLIVE TICKETMASTER EVENTS:\n{json.dumps(safe_events_data) if isinstance(safe_events_data, list) else safe_events_data}"}
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

def match_photos_to_results(recommendations, raw_places, live_events=None):
    # Build event image lookup keyed by normalised title
    event_images = {}
    for ev in (live_events or []):
        title = ev.get('title', '').lower().replace(' ', '')
        if title and ev.get('image_url'):
            event_images[title] = ev['image_url']

    # Build Google Places photo lookup (validated via HEAD request)
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

        # 1. Exact event title match
        if rec_name in event_images:
            rec['photo_url'] = event_images[rec_name]
            continue

        # 2. Partial event title match
        ev_matched = False
        for ev_title, ev_img in event_images.items():
            if ev_title in rec_name or rec_name in ev_title:
                rec['photo_url'] = ev_img
                ev_matched = True
                break
        if ev_matched:
            continue

        # 3. Google Places exact match
        if rec_name in place_photos:
            rec['photo_url'] = place_photos[rec_name]
            continue

        # 4. Google Places partial match
        matched = False
        for place_name, url in place_photos.items():
            if place_name in rec_name or rec_name in place_name:
                rec['photo_url'] = url
                matched = True
                break
        if not matched:
            rec['photo_url'] = None

    return recommendations

def render_spot_card(spot, location_input, user_id, index, mode):
    title_prefix = f"{index}." if mode == "top_3" else "🎲"

    search_term = spot['name'].replace(' ', '+') + f"+{location_input.replace(' ', '+')}"
    map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
    encoded_address = urllib.parse.quote(spot['address'])
    uber_url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_address}"

    # Fallback image (priority: category → tier_name → why_its_perfect → name)
    text_to_check = " ".join([
        (spot.get('name', '') or ''),
        (spot.get('category', '') or ''),
        (spot.get('tier_name', '') or ''),
        (spot.get('why_its_perfect', '') or ''),
    ]).lower()
    if any(k in text_to_check for k in ["wine", "winery", "vineyard", "sommelier"]):
        fallback_url = "https://images.unsplash.com/photo-1510812431401-41d2bd2722f3?w=800&q=80"
    elif any(k in text_to_check for k in ["brewery", "brewing", "brewpub", "craft beer", "taproom"]):
        fallback_url = "https://images.unsplash.com/photo-1575367439058-6096bb9cf5e2?w=800&q=80"
    elif any(k in text_to_check for k in ["cocktail", "speakeasy", "lounge", " bar", " pub"]):
        fallback_url = "https://images.unsplash.com/photo-1575367439058-6096bb9cf5e2?w=800&q=80"
    elif any(k in text_to_check for k in ["coffee", "cafe", "espresso", "tea"]):
        fallback_url = "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=800&q=80"
    elif any(k in text_to_check for k in ["concert", "live music", "jazz", "band", "music venue", "performance"]):
        fallback_url = "https://images.unsplash.com/photo-1540039155732-d68a96670afb?w=800&q=80"
    elif any(k in text_to_check for k in ["theater", "comedy", "cinema", "show"]):
        fallback_url = "https://images.unsplash.com/photo-1507676184212-d03ab07a01bf?w=800&q=80"
    elif any(k in text_to_check for k in ["museum", "gallery", "art", "exhibit", "culture"]):
        fallback_url = "https://images.unsplash.com/photo-1554907984-15263bfd63bd?w=800&q=80"
    elif any(k in text_to_check for k in ["park", "garden", "outdoor", "nature", "trail", "hiking"]):
        fallback_url = "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800&q=80"
    elif any(k in text_to_check for k in ["restaurant", "dining", "food", "bistro", "kitchen", "eatery"]):
        fallback_url = "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&q=80"
    elif any(k in text_to_check for k in ["bowling", "escape room", "arcade", "entertainment", "activity"]):
        fallback_url = "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?w=800&q=80"
    else:
        fallback_url = "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800&q=80"

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
    _score = spot.get('spontaneity_score') or 0
    try: _score = int(_score)
    except: _score = 0
    if _score >= 7:
        spontaneity_badge = ' <span style="font-size:0.65rem;background:#e65100;color:#fff;padding:2px 7px;border-radius:10px;font-weight:700;vertical-align:middle;">🔥 Wild Choice</span>'
    elif _score >= 4:
        spontaneity_badge = ' <span style="font-size:0.65rem;background:#1565c0;color:#fff;padding:2px 7px;border-radius:10px;font-weight:700;vertical-align:middle;">⚡ Interesting Pick</span>'
    else:
        spontaneity_badge = ''

    # Event time line shown below venue name (Ticketmaster events only)
    is_event = bool(spot.get('image_url')) or any(k in (category or '') for k in ['Event', 'Music', 'Sports', 'Concert', 'Arts'])
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
    <div class="wc-tier">✦ {tier_name}</div>
  </div>
  <div class="wc-body">
    <div class="wc-name">{title_prefix} {spot['name']}</div>
    <div class="wc-meta">{category} • ✨ {vibe}{spontaneity_badge}</div>
    {event_time_html}<div class="wc-address">📍 {address}</div>
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
        with col1:
            if st.button("⭐ Save", key=f"save_{index}_{spot['name']}", use_container_width=True, help="Save for later"):
                save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'))
                award_points(user_id, "save", 1, "Saved a spot")
                check_and_award_badges(user_id)
        with col2:
            if st.button("✅ I'm Going", key=f"going_{index}_{spot['name']}", use_container_width=True, type="primary", help="Mark as chosen"):
                save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'), notes="chosen")
                award_points(user_id, "going", 5, "Chose an outing")
                check_and_award_badges(user_id)
        with col3:
            if st.button("👎 Not for me", key=f"nope_{index}_{spot['name']}", use_container_width=True, help="Never suggest this again"):
                save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'), rating=1, notes="Blacklisted via quick-button.")

# ==========================================
# 5. ASYNC DATA GATHERER
# ==========================================
async def gather_all_data(lat, lng, semantic_query, distance, target_date_str, user_id, specific_keyword=""):
    async def _events_with_timeout():
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fetch_live_events, lat, lng, distance, target_date_str, specific_keyword),
                timeout=5.0
            )
        except (asyncio.TimeoutError, Exception):
            return []

    weather_task   = asyncio.to_thread(get_live_weather, lat, lng)
    places_task    = asyncio.to_thread(fetch_places_semantic, semantic_query, lat, lng, distance)
    excluded_task  = asyncio.to_thread(get_excluded_spots, user_id)
    favorites_task = asyncio.to_thread(get_favorite_spots, user_id)
    prefs_task     = asyncio.to_thread(get_user_preference_scores, user_id)
    return await asyncio.gather(weather_task, places_task, _events_with_timeout(), excluded_task, favorites_task, prefs_task)

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
            if _should_show_wild_idea(user_profile):
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

                    _idea = get_wild_idea(
                        str(st.session_state.user.id), _wi_lat, _wi_lng, _wi_loc, _prof_summary
                    )
                    if _idea:
                        st.markdown(f"""
<div style="background:linear-gradient(135deg,#2d6a4f 0%,#52b788 100%);color:white;border-radius:12px;padding:16px 20px;margin-bottom:8px;">
  <div style="font-size:0.72rem;font-weight:700;letter-spacing:1.2px;opacity:0.85;margin-bottom:6px;">💡 HERE'S A WILD IDEA...</div>
  <div style="font-size:1.1rem;font-weight:700;margin-bottom:3px;">{_idea['emoji']} {_idea['name']}</div>
  <div style="font-size:0.88rem;opacity:0.92;">{_idea['why_now']}</div>
</div>""", unsafe_allow_html=True)
                        _wi_col1, _wi_col2, _wi_col3 = st.columns([2, 1, 3])
                        with _wi_col1:
                            if st.button("🎲 Let's Do It", key="wild_idea_go", type="primary", use_container_width=True):
                                _dismiss_wild_idea(st.session_state.user.id)
                                award_points(st.session_state.user.id, "wild_idea", 3, "Completed a Here's a Wild Idea")
                                st.session_state.mem_spec  = _idea['name']
                                st.session_state.current_mode = "get_wild"
                                st.session_state.filters_dict = {
                                    "group":    st.session_state.mem_group,
                                    "time":     f"{st.session_state.mem_day} ({st.session_state.mem_time})",
                                    "vibe":     st.session_state.mem_vibe,
                                    "food":     st.session_state.mem_food,
                                    "specific": _idea['name'],
                                    "spend":    st.session_state.mem_spend,
                                }
                                st.session_state.search_active = True
                                st.session_state.trigger_fetch = True
                                st.session_state.session_seen_spots = []
                                st.rerun()
                        with _wi_col2:
                            if st.button("✕ Dismiss", key="wild_idea_dismiss", use_container_width=True):
                                _dismiss_wild_idea(st.session_state.user.id)
                                st.rerun()
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

            col_day, col_time = st.columns(2)
            day_index = 0 if st.session_state.mem_day == "☀️ Today" else 1
            time_index = 0 if st.session_state.mem_time == "☀️ Daytime" else 1
            
            with col_day: 
                ui_day = st.radio("Day", ["☀️ Today", "📅 Tomorrow"], index=day_index, horizontal=True, label_visibility="collapsed")
            with col_time: 
                ui_time = st.radio("Time", ["☀️ Daytime", "🌙 Night"], index=time_index, horizontal=True, label_visibility="collapsed")
            
            intended_time = f"{ui_day} ({ui_time})"

            st.write("") 
            col_group, col_vibe = st.columns(2)
            
            group_options = ["Date", "Family Outing", "Friends", "Solo"]
            with col_group: 
                ui_group = st.selectbox("Who is going?", group_options, index=group_options.index(st.session_state.mem_group))
            
            vibe_options = ["Doesn't Matter", "Outside", "Inside"]
            with col_vibe: 
                ui_vibe = st.radio("Setting?", vibe_options, index=vibe_options.index(st.session_state.mem_vibe), horizontal=True)
            
            st.write("")
            col_food, col_dist = st.columns(2)

            food_options = ["Full Meal", "Just Drinks/Coffee", "No Food Needed"]
            with col_food:
                ui_food = st.selectbox("Sustenance?", food_options, index=food_options.index(st.session_state.mem_food))
            with col_dist:
                ui_dist = st.slider("Max Distance (Miles)", 1, 20, st.session_state.mem_dist)

            spend_options = ["🆓 Free", "$ Affordable", "$ Moderate", "$$ Splurge"]
            ui_spend = st.radio("Budget?", spend_options, index=spend_options.index(st.session_state.mem_spend), horizontal=True)

            with st.expander("Need something specific? (Optional)", expanded=False):
                ui_spec = st.text_input("Keyword", value=st.session_state.mem_spec, placeholder="e.g., 'romantic', 'live jazz', 'large group'", label_visibility="collapsed")

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
                        semantic_query = build_semantic_query(st.session_state.filters_dict, user_profile, pref_scores_pre)

                        status_loader.info("☁️ Curating local weather, places, and events...")
                        def _run_gather():
                            return gather_all_data(
                                lat, lng, semantic_query, st.session_state.mem_dist,
                                target_date_str, st.session_state.user.id,
                                specific_keyword=st.session_state.filters_dict.get('specific', '')
                            )
                        try:
                            weather_report, raw_places, live_events_data, db_excluded, user_favorites, pref_scores = asyncio.run(_run_gather())
                        except RuntimeError:
                            import nest_asyncio
                            nest_asyncio.apply()
                            weather_report, raw_places, live_events_data, db_excluded, user_favorites, pref_scores = asyncio.run(_run_gather())

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
                            if st.session_state.current_mode == "get_wild":
                                selected_tiers = None
                            else:
                                _fd = st.session_state.filters_dict
                                _pool = list(TIER_PERSONALITIES)
                                _boosts = []
                                _tier_by_name = {t['tier_name']: t for t in TIER_PERSONALITIES}
                                def _boost(*names):
                                    for n in names:
                                        if n in _tier_by_name:
                                            _boosts.extend([_tier_by_name[n]] * 2)
                                if _fd.get('group') == 'Date':
                                    _boost('The Date Night Pick', 'The Hidden Gem', 'The Comeback Kid')
                                elif _fd.get('group') == 'Friends':
                                    _boost('The Wild Card', 'The Local Favorite', 'The Adventure')
                                elif _fd.get('group') == 'Family Outing':
                                    _boost('The Crowd-Pleaser', 'The Local Favorite', 'The Underdog')
                                if _fd.get('spend') == '$$ Splurge':
                                    _boost('The Date Night Pick', 'The Comeback Kid')
                                elif _fd.get('spend') == '🆓 Free':
                                    _boost('The Hidden Gem', 'The Adventure', 'The Underdog')
                                selected_tiers = random.sample(_pool + _boosts, 3)
                            ai_results = get_ai_recommendations(
                                raw_places, live_events_data, weather_report,
                                st.session_state.filters_dict, location_context,
                                target_date_str, relative_day, user_profile, all_excluded,
                                user_favorites, mode=st.session_state.current_mode,
                                tier_personalities=selected_tiers,
                                lat=lat, lng=lng, radius_miles=st.session_state.mem_dist,
                                preference_scores=pref_scores
                            )
                            match_photos_to_results(ai_results.get('recommendations', []), raw_places, live_events_data)
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
                            if new_rating >= 4:
                                award_points(st.session_state.user.id, "rating", 1, "Rated a visit")
                            st.success("Feedback saved!")
                            st.session_state.saved_spots_dirty = True
                            st.rerun()

                    if st.button("🗑️ Delete Spot", key=f"del_{saved['id']}"):
                        if delete_spot_from_db(saved['id']):
                            st.session_state.saved_spots_dirty = True
                            st.rerun()