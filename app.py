import hashlib
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
from dateutil import parser as dateutil_parser
from streamlit_geolocation import streamlit_geolocation
from supabase import create_client, Client
from tenacity import retry, wait_exponential, stop_after_attempt

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]
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
    .hero-header { text-align: center; padding: 2rem 0 1rem 0; }
    .hero-title { color: #2e7d32; font-family: 'Helvetica Neue', sans-serif; font-size: 3.5rem; font-weight: 800; letter-spacing: -1px; text-transform: uppercase; margin-bottom: 0; line-height: 1.1; }
    .hero-subtitle { color: #558b2f; font-size: 1.2rem; font-weight: 400; letter-spacing: 1px; margin-top: 10px; }
    
    .wild-card { background: #ffffff; border: 1px solid #e0e0e0; border-radius: 16px; overflow: hidden; margin-top: 20px; margin-bottom: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.06); animation: fadeSlideUp 0.6s ease-out forwards; }
    .get-wild-special { border: 2px solid #FFD700; box-shadow: 0 0 20px rgba(255, 215, 0, 0.4); background: linear-gradient(145deg, #fffdf0, #ffffff); }
    
    .wild-card-img { width: 100%; height: 220px; object-fit: cover; }
    .wild-card-content { padding: 20px; }
    .spot-category { color: #558b2f; font-weight: 700; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 1px; margin-bottom: 5px; display: block; }
    .spot-title { font-size: 1.5rem; font-weight: 700; color: #1a1a1a; margin-top: 0; margin-bottom: 5px; }
    .spot-meta { font-size: 0.9rem; color: #666; margin-bottom: 15px; }
    .spot-pitch { font-size: 1.05rem; line-height: 1.5; color: #333; margin-bottom: 20px; }
    
    .tag-pill { display: inline-block; background-color: #e8f5e9; color: #2e7d32; padding: 4px 12px; border-radius: 16px; font-size: 0.8rem; font-weight: 600; margin-right: 6px; margin-bottom: 12px; border: 1px solid #c8e6c9; }
    
    .icon-btn-row { display: flex; gap: 15px; margin-bottom: 10px; border-top: 1px solid #eee; padding-top: 15px; }
    .icon-btn { font-size: 1.6rem; text-decoration: none; transition: transform 0.2s; cursor: pointer; display: inline-block; }
    .icon-btn:hover { transform: scale(1.15); }
    
    @keyframes fadeSlideUp { from {opacity: 0; transform: translateY(20px);} to { opacity: 1; transform: translateY(0); } }
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

# Persistent memory state variables
if 'mem_loc' not in st.session_state: st.session_state.mem_loc = ""
if 'mem_day' not in st.session_state: st.session_state.mem_day = "☀️ Today"
if 'mem_time' not in st.session_state: st.session_state.mem_time = "🌙 Night"
if 'mem_group' not in st.session_state: st.session_state.mem_group = "Date"
if 'mem_vibe' not in st.session_state: st.session_state.mem_vibe = "Doesn't Matter"
if 'mem_food' not in st.session_state: st.session_state.mem_food = "Full Meal"
if 'mem_dist' not in st.session_state: st.session_state.mem_dist = 5
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
    raw = json.dumps(filters_dict, sort_keys=True) + location_name + target_date_str + mode
    return hashlib.md5(raw.encode()).hexdigest()

def delete_spot_from_db(spot_id):
    try:
        st.write(f"Attempting to delete id: {spot_id}")
        response = supabase.table('saved_spots').delete().eq('id', spot_id).execute()
        st.write(f"Delete response: {response}")
        st.toast("🗑️ Spot permanently deleted.")
        return True
    except Exception as e:
        st.error(f"Database error while deleting: {e}")
        return False

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

def build_semantic_query(filters_dict, profile):
    modifiers = []
    
    # Highest priority: The Specific Keyword
    if filters_dict.get('specific'):
        modifiers.append(filters_dict['specific'])

    if profile:
        if profile.get('needs_dog_friendly') and filters_dict['vibe'] == "Outside": modifiers.append("dog-friendly")
        if profile.get('vibe_preference'): modifiers.append(profile.get('vibe_preference'))

    if filters_dict['group'] == "Date": modifiers.append("intimate")
    elif filters_dict['group'] == "Family Outing": modifiers.append("kid-friendly")
    elif filters_dict['group'] == "Friends": modifiers.append("lively")

    modifier_str = " ".join(modifiers)
    
    # Always keep a strong base category so Google doesn't return random offices/services
    if filters_dict['vibe'] == "Outside":
        if filters_dict['food'] == "Full Meal": base = "restaurants with nice patios"
        elif filters_dict['food'] == "Just Drinks/Coffee": base = "wineries, cocktail bars with patios, or upscale breweries"
        else: base = "botanical gardens, scenic views, or parks"
    else:
        if filters_dict['food'] == "Full Meal": base = "highly rated restaurants"
        elif filters_dict['food'] == "Just Drinks/Coffee": base = "wine bars, speakeasies, or lounges"
        else: base = "entertainment, museums, or unique attractions"
            
    return f"{modifier_str} {base}".strip()

def fetch_places_semantic(semantic_query, lat, lng, radius_miles):
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.websiteUri,places.photos,places.editorialSummary,places.location"
    }
    radius_meters = int(radius_miles * 1609.34)
    data = {
        "textQuery": semantic_query,
        "pageSize": 8,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius_meters}}
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        if response.status_code == 200:
            return response.json().get('places', [])
    except: pass
    return []

def fetch_live_events(location_name, intended_time, group_type, target_date_str, relative_day, lat, lng):
    import re

    US_STATES = {
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York",
        "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
        "West Virginia", "Wisconsin", "Wyoming"
    }

    try:
        state_abbr, state_name = get_state_from_coords(lat, lng)
        search_location = state_name if state_name else location_name

        try:
            target_date = dateutil_parser.parse(target_date_str).date()
        except:
            target_date = None

        url = "https://api.tavily.com/search"
        queries = [
            f"live music concerts events {target_date_str} {search_location}",
            f"festivals theater shows activities {target_date_str} {search_location}"
        ]

        validated_results = []

        for query in queries:
            payload = {
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced",
                "include_answer": False,
                "max_results": 5
            }
            try:
                response = requests.post(url, json=payload, timeout=15)
                data = response.json()
                results = data.get('results', [])

                for r in results:
                    snippet = r.get('content', '') or ''
                    title = r.get('title', '')
                    result_url = r.get('url', '')

                    # Reject results that mention another US state without mentioning our target state
                    if state_name:
                        foreign_state_only = False
                        for state in US_STATES:
                            if state != state_name and state.lower() in snippet.lower():
                                if (state_name.lower() not in snippet.lower() and
                                        (not state_abbr or state_abbr not in snippet)):
                                    foreign_state_only = True
                                    break
                        if foreign_state_only:
                            continue

                    # Validate date against target
                    date_verified = False
                    if target_date:
                        date_patterns = re.findall(
                            r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
                            r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
                            r'\s+\d{1,2}(?:,?\s*\d{4})?\b',
                            snippet, re.IGNORECASE
                        )
                        for dp in date_patterns:
                            try:
                                parsed = dateutil_parser.parse(
                                    dp, default=datetime(target_date.year, 1, 1)
                                ).date()
                                if parsed == target_date:
                                    date_verified = True
                                    break
                            except:
                                pass

                    validated_results.append({
                        "title": title,
                        "venue_name": "",
                        "venue_address": "",
                        "date_str": target_date_str,
                        "start_time": "",
                        "date_verified": date_verified,
                        "url": result_url,
                        "snippet": snippet[:500]
                    })
            except:
                continue

        return validated_results
    except:
        return []

@retry(wait=wait_exponential(min=1, max=10), stop=stop_after_attempt(3))
def get_ai_recommendations(raw_places, live_events_data, weather_report, filters_dict, location_name, target_date_str, relative_day, profile, excluded_spots, favorite_spots, mode="top_3"):
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
        history_context = f"\nUSER'S HISTORICAL FAVORITES (Learn from their taste!): {', '.join(favorite_spots)}" if favorite_spots else ""
        profile_context = f"\nUSER BASELINE PROFILE:\n{stroller}\n{dog}\n{vibe_pref}{history_context}"

    blacklist_context = f"CRITICAL: DO NOT RECOMMEND ANY OF THESE PLACES: {', '.join(excluded_spots)}" if excluded_spots else ""

    if mode == "get_wild":
        instruction = """Select EXACTLY ONE option from the data. Assign it the category: 'Spontaneous Adventure'."""
    else:
        instruction = """
        Return EXACTLY 3 options from the data, providing STRICT VARIETY (do not return 3 of the exact same type of venue). 
        Assign each to one of these directional 'tier_name' categories:
        1. 'The Crowd-Pleaser': A highly rated, established safe bet that closely aligns with their profile and past favorites.
        2. 'The Fresh Take': A live event from the web search, a trending new spot, or something catching on.
        3. 'The Hidden Gem': Something quirky, unique, or slightly off the beaten path.
        """

    if filters_dict.get('vibe') == "Outside":
        weather_rule = "3. WEATHER PIVOT: If weather report indicates RAIN, SNOW, or TEMP < 45°F, prioritize indoor venues or those with heated patios."
    else:
        weather_rule = "3. WEATHER: Do not restrict recommendations or warn the user about weather, as the user is open to indoor venues or specifically requested them."

    specific_rule = ""
    if filters_dict.get('specific'):
        specific_rule = f"5. MANDATORY SPECIFIC REQUIREMENT: The user explicitly requested '{filters_dict['specific']}'. EVERY recommendation MUST align with this vibe. Pluck the 2-3 most important keywords from this request and output them in the 'matched_tags' array."

    system_prompt = f"""
    You are a luxury local concierge for an app called 'Get Wild'.
    
    CRITICAL CONTEXT:
    - Target Location: {location_name}
    - CURRENT WEATHER: {weather_report}
    - TARGET EVENT DATE: {target_date_str} ({relative_day})
    - User Intended Time: {filters_dict['time']}
    - Session Profile: {filters_dict['group']} looking for {filters_dict['food']} in a {filters_dict['vibe']} setting.
    {profile_context}
    {blacklist_context}
    
    GEOGRAPHY, WEATHER & EVENT SHACKLES:
    1. SUPER STRICT GEOGRAPHY: EVERY recommendation MUST be physically located in or within 20 miles of {location_name}. Discard any web events outside this immediate area.
    2. STRICT EVENT DETAILS: If recommending a live event, verify it is happening {relative_day} ({target_date_str}). The 'why_its_perfect' field MUST start with the exact time and venue.
    {weather_rule}
    4. ANTI-HALLUCINATION (CRITICAL): DO NOT guess addresses. You MUST use the EXACT 'formattedAddress' and 'websiteUri' provided in the Google Places JSON or the Web Search data.
    {specific_rule}

    STRICT EVENT EVALUATION RULES:
    5. DATE GATING: ONLY use events where date_verified=True. Completely discard any event with date_verified=False — do not mention or recommend them.
    6. EVENT VENUE MANDATE: When recommending any live event, the 'why_its_perfect' field MUST include the venue name AND full venue address extracted from the event data or snippet.
    7. NO-EVENTS FALLBACK: If zero events have date_verified=True, do NOT fabricate event details. Fall back exclusively to Google Places data for all recommendations.
    
    {instruction}
    
    Return STRICTLY as a JSON object with a 'recommendations' array containing:
    'name', 'tier_name' (e.g., The Crowd-Pleaser), 'category', 'address' (Exact from data), 'why_its_perfect' (2-3 sentences), 'vibe_check' (3 words), 'matched_tags' (Array of 2-3 strings highlighting the specific keywords you honored, e.g., ["Romantic", "Good Wine"]. Leave empty if no specific keyword was given.), 'website' (URL if available), 'photo_ref' (String from places.photos[0].name if available), 'lat' (float), and 'lng' (float).
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"GOOGLE PLACES DATA: {json.dumps(trimmed_places)}\n\nLIVE WEB SEARCH EVENTS:\n{json.dumps(safe_events_data) if isinstance(safe_events_data, list) else safe_events_data}"}
        ],
        max_tokens=2500 
    )
    
    raw_content = response.choices[0].message.content.strip()
    if raw_content.startswith("```json"):
        raw_content = raw_content[7:-3].strip()
    elif raw_content.startswith("```"):
        raw_content = raw_content[3:-3].strip()
        
    return json.loads(raw_content)

def render_spot_card(spot, location_input, user_id, index, mode):
    title_prefix = f"{index}." if mode == "top_3" else "🎲"
    special_class = "get-wild-special" if mode == "get_wild" else ""

    search_term = spot['name'].replace(' ', '+') + f"+{location_input.replace(' ', '+')}"
    map_url = f"https://www.google.com/maps/search/?api=1&query={search_term}"
    encoded_address = urllib.parse.quote(spot['address'])
    uber_url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_address}"
    
    raw_share_text = f"Let's go to {spot['name']}!\n📍 {spot['address']}\n🗺️ {map_url}"
    encoded_share = urllib.parse.quote(raw_share_text)
    sms_url = f"sms:?&body={encoded_share}"
    email_url = f"mailto:?subject={urllib.parse.quote('Wild Plan: ' + spot['name'])}&body={encoded_share}"
    
    if spot.get('photo_ref'):
        img_url = f"https://places.googleapis.com/v1/{spot['photo_ref']}/media?key={GOOGLE_API_KEY}&maxHeightPx=400&maxWidthPx=800"
    else:
        text_to_check = f"{spot['name']} {spot.get('category', '')} {spot.get('why_its_perfect', '')}".lower()
        if "comedy" in text_to_check or "stand-up" in text_to_check or "laugh" in text_to_check:
            img_url = "https://images.unsplash.com/photo-1585699324551-f6c309eedeca?w=800&q=80" 
        elif "outdoor" in text_to_check or "amphitheater" in text_to_check or "festival" in text_to_check:
            img_url = "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800&q=80" 
        elif "music" in text_to_check or "concert" in text_to_check or "jazz" in text_to_check or "band" in text_to_check:
            img_url = "https://images.unsplash.com/photo-1540039155732-d68a96670afb?w=800&q=80" 
        else:
            img_url = "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800&q=80" 
            
    img_html = f'<img src="{img_url}" class="wild-card-img">'
    website_icon = f'<a href="{spot["website"]}" target="_blank" class="icon-btn" title="Visit Website">🌐</a>' if spot.get('website') else ""

    # Generate visual tag pills based on what the AI learned
    tags_html = ""
    if spot.get('matched_tags'):
        for tag in spot['matched_tags']:
            tags_html += f'<span class="tag-pill">✓ {tag}</span>'

    html_card = f"""
<div class="wild-card {special_class}">
{img_html}
<div class="wild-card-content">
<span class="spot-category" style="color:#d84315;">{spot.get('tier_name', 'Top Pick')}</span> • <span class="spot-category">{spot.get('category', '')}</span>
<h2 class="spot-title">{title_prefix} {spot['name']}</h2>
<div class="spot-meta">📍 {spot['address']} | ✨ <b>{spot['vibe_check']}</b></div>
<div>{tags_html}</div>
<p class="spot-pitch">{spot['why_its_perfect']}</p>
<div class="icon-btn-row">
<a href="{map_url}" target="_blank" class="icon-btn" title="View on Maps">🗺️</a>
{website_icon}
<a href="{uber_url}" target="_blank" class="icon-btn" title="Ride with Uber">🚗</a>
<a href="{sms_url}" class="icon-btn" title="Share via Text">💬</a>
<a href="{email_url}" class="icon-btn" title="Share via Email">✉️</a>
</div>
</div>
</div>
"""
    st.markdown(html_card, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("🔖 Save to List", key=f"save_{index}_{spot['name']}"):
            save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'))
    with col2:
        if st.button("🚫 Not for me", key=f"hate_{index}_{spot['name']}"):
            save_spot_to_db(user_id, spot['name'], spot['address'], spot.get('category', 'Top Pick'), rating=1, notes="Blacklisted via quick-button.")

# ==========================================
# 5. ASYNC DATA GATHERER 
# ==========================================
async def gather_all_data(lat, lng, semantic_query, distance, location_input, intended_time, group_type, target_date_str, relative_day):
    weather_task = asyncio.to_thread(get_live_weather, lat, lng)
    places_task = asyncio.to_thread(fetch_places_semantic, semantic_query, lat, lng, distance)
    events_task = asyncio.to_thread(fetch_live_events, location_input if location_input else "nearby", intended_time, group_type, target_date_str, relative_day, lat, lng)
    return await asyncio.gather(weather_task, places_task, events_task)

# ==========================================
# 6. UI ROUTING
# ==========================================
st.markdown("""
<div class="hero-header">
    <h1 class="hero-title">Get Wild</h1>
    <p class="hero-subtitle">Disconnect. Explore. Connect.</p>
</div>
""", unsafe_allow_html=True)

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
                    st.rerun()
                except Exception as e: st.error("Login failed. Check your credentials.")

    with tab_signup:
        with st.form("signup_form"):
            email_signup = st.text_input("Email (New Account)")
            password_signup = st.text_input("Password (New Account)", type="password")
            if st.form_submit_button("Sign Up", type="primary", use_container_width=True):
                try:
                    res = supabase.auth.sign_up({"email": email_signup, "password": password_signup})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e: st.error(f"Signup failed: {e}")

else:
    tab_explore, tab_profile, tab_saved = st.tabs(["🌍 Explore", "👤 My Profile", "⭐ Saved Spots"])

    with tab_explore:
        user_profile = get_profile(st.session_state.user.id)
        
        # --- SCREEN 1: THE INPUT FORM ---
        if not st.session_state.search_active:
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

            with st.expander("Need something specific? (Optional)", expanded=False):
                ui_spec = st.text_input("Keyword", value=st.session_state.mem_spec, placeholder="e.g., 'romantic', 'live jazz', 'large group'", label_visibility="collapsed")

            st.write("---")
            
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1: top_3_clicked = st.button("🌟 Top 3 Recommendations", use_container_width=True)
            with btn_col2: get_wild_clicked = st.button("🎲 GET WILD", type="primary", use_container_width=True)

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
                    
                    st.session_state.current_mode = "get_wild" if get_wild_clicked else "top_3"
                    st.session_state.filters_dict = {
                        "group": ui_group, "time": intended_time, 
                        "vibe": ui_vibe, "food": ui_food, 
                        "specific": ui_spec
                    }
                    st.session_state.search_active = True
                    st.session_state.trigger_fetch = True
                    st.session_state.session_seen_spots = [] 
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
                        semantic_query = build_semantic_query(st.session_state.filters_dict, user_profile)
                        
                        status_loader.info("☁️ Curating local weather, places, and events...")
                        weather_report, raw_places, live_events_data = asyncio.run(
                            gather_all_data(lat, lng, semantic_query, st.session_state.mem_dist, location_context, st.session_state.filters_dict['time'], st.session_state.filters_dict['group'], target_date_str, relative_day)
                        )
                        
                        if st.session_state.current_mode == "get_wild":
                            status_loader.info("🎲 Loading up your adventure and revealing the spontaneity...")
                        else:
                            status_loader.info("🗺️ Assembling your perfect itinerary...")
                        
                        db_excluded = get_excluded_spots(st.session_state.user.id)
                        all_excluded = list(set(db_excluded + st.session_state.session_seen_spots))
                        
                        # NEW: Fetch favorites to feed the AI
                        user_favorites = get_favorite_spots(st.session_state.user.id)
                        
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

                        if cached_result:
                            st.session_state.current_results = cached_result
                        else:
                            st.session_state.current_results = get_ai_recommendations(
                                raw_places, live_events_data, weather_report,
                                st.session_state.filters_dict, location_context,
                                target_date_str, relative_day, user_profile, all_excluded,
                                user_favorites, mode=st.session_state.current_mode
                            )
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
                    error_type = type(e).__name__
                    status_loader.error(f"Error connecting to the wild. Try again! ({error_type})")

            if st.session_state.current_results:
                st.write("---")
                results = st.session_state.current_results
                mode = st.session_state.current_mode
                
                # --- PYDECK INTERACTIVE MAP WITH HOVER TOOLTIPS ---
                map_data = []
                for i, spot in enumerate(results.get("recommendations", [])):
                    if spot.get('lat') and spot.get('lng'):
                        display_name = f"{i+1}. {spot['name']}" if mode == "top_3" else f"🎲 {spot['name']}"
                        map_data.append({"lat": spot['lat'], "lon": spot['lng'], "name": display_name})
                
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
                
                # --- RENDER CARDS ---
                for index, spot in enumerate(results.get("recommendations", [])):
                    render_spot_card(spot, st.session_state.mem_loc, st.session_state.user.id, index + 1, mode)
                    
                # --- SHUFFLE BUTTON (ONLY IN TOP 3 MODE) ---
                if mode == "top_3":
                    st.write("---")
                    if st.button("🔀 Shuffle", use_container_width=True):
                        st.session_state.trigger_fetch = True
                        st.rerun()

    # ----------------------------------------
    # TAB 2 & 3: PROFILE & SAVED SPOTS 
    # ----------------------------------------
    with tab_profile:
        current_prof = get_profile(st.session_state.user.id) or {}
        st.markdown(f"### 🏆 Get Wild Tally: **{current_prof.get('wild_tally', 0)}**")
        st.write("Save spots to increase your tally and build your exploration streak!")
        st.write("---")
        st.subheader("Personalize Your Profile")
        st.write("Set your baseline preferences so the app learns how you like to explore.")
        
        with st.form("profile_form"):
            fname = st.text_input("First Name", value=current_prof.get('first_name', ''))
            pname = st.text_input("Partner/Spouse Name (Optional)", value=current_prof.get('partner_name', ''))
            stroller = st.checkbox("Require Stroller Accessibility", value=current_prof.get('needs_stroller_access', False))
            dog = st.checkbox("Require Dog-Friendly Patios", value=current_prof.get('needs_dog_friendly', False))
            vibe_pref = st.text_area("What is your ideal aesthetic? (e.g., 'Warm, modern, naturalistic')", value=current_prof.get('vibe_preference', ''))
            
            if st.form_submit_button("Save Profile", type="primary"):
                supabase.table('user_profiles').upsert({
                    'id': st.session_state.user.id, 'first_name': fname, 'partner_name': pname,
                    'needs_stroller_access': stroller, 'needs_dog_friendly': dog, 'vibe_preference': vibe_pref
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
            for saved in saved_spots:
                icon = "🚫" if saved['rating'] == 1 else "📍"
                with st.expander(f"{icon} {saved['spot_name']}"):
                    st.caption(saved['address'])

                    with st.form(f"rate_form_{saved['id']}"):
                        current_rating = saved['rating'] if saved['rating'] else 3
                        new_rating = st.slider("Rate this spot (1-5 Stars. 1 = Blacklist)", 1, 5, current_rating)
                        notes = st.text_input("Private Notes", value=saved.get('user_notes', ''))

                        if st.form_submit_button("Update Feedback", type="primary"):
                            supabase.table('saved_spots').update({'rating': new_rating, 'user_notes': notes}).eq('id', saved['id']).execute()
                            st.success("Feedback saved!")
                            st.session_state.saved_spots_dirty = True
                            st.rerun()

                    if st.button("🗑️ Delete Spot", key=f"del_{saved['id']}"):
                        if delete_spot_from_db(saved['id']):
                            st.session_state.saved_spots_dirty = True
                            st.rerun()