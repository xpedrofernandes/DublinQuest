/* Same-origin APIs own validation, spatial queries, selection and persistence.
   Leaflet consumes returned WGS84 GeoJSON; imported text is never HTML. */
'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const labels = {street_art: 'Street art', public_art: 'Public art', heritage: 'Heritage', park: 'Parks'};
  const state = {start: null, adventure: null, csrf: null, busy: false, savedNext: null, walking: null, walkingVisible: false, geometryKey: null};
  let map, startMarker, radiusLayer, adventureLayer, spatialLayer, walkingLayer;
  const stopMarkers = new Map();

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function button(text, action, className = 'text-button') {
    const element = node('button', text, className);
    element.type = 'button';
    element.addEventListener('click', action);
    return element;
  }
  function tell(message, error = false) {
    $('feedback').textContent = message;
    $('feedback').classList.toggle('error', error);
    if (error) $('feedback').focus();
  }
  function flattenErrors(value) {
    if (Array.isArray(value)) return value.map(flattenErrors).join(' ');
    if (value && typeof value === 'object') return Object.entries(value).map(([key, detail]) => `${key === 'detail' || key === 'non_field_errors' ? '' : key + ': '}${flattenErrors(detail)}`).join(' ');
    return String(value);
  }
  async function api(url, method = 'GET', body) {
    const headers = {'Accept': 'application/json'};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET') headers['X-CSRFToken'] = state.csrf;
    let response;
    try {
      response = await fetch(url, {method, headers, credentials: 'same-origin', cache: 'no-store', body: body === undefined ? undefined : JSON.stringify(body)});
    } catch { throw new Error('Unable to reach DublinQuest. Check your connection and try again.'); }
    if (response.status === 204) return null;
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 403) throw new Error('Your security token may have expired. Reload this page before trying again.');
      throw new Error(data ? flattenErrors(data) : `The server returned ${response.status}. Please try again.`);
    }
    return data;
  }
  // Serialize UI requests so old responses cannot overwrite a later selection.
  async function run(message, action) {
    if (state.busy) return;
    state.busy = true;
    document.body.classList.add('busy');
    document.querySelector('main').setAttribute('aria-busy', 'true');
    const controls = [...document.querySelectorAll('main button, main input, main select')];
    const disabled = controls.map(control => control.disabled);
    controls.forEach(control => { control.disabled = true; });
    tell(message);
    try { await action(); }
    catch (error) { tell(error.message, true); }
    finally {
      controls.forEach((control, index) => { control.disabled = disabled[index]; });
      document.body.classList.remove('busy');
      document.querySelector('main').removeAttribute('aria-busy');
      state.busy = false;
      updateStartControls();
    }
  }
  function updateStartControls() {
    for (const id of ['generate', 'nearby', 'intersections']) $(id).disabled = !state.start || !state.csrf || state.busy;
  }
  function categories() { return [...document.querySelectorAll('[name="category"]:checked')].map(input => input.value); }
  function criteria() {
    if (!state.start) throw new Error('Choose a starting point using the map or place search.');
    const selected = categories();
    if (!selected.length) throw new Error('Choose at least one category.');
    return {lat: state.start.lat, lng: state.start.lng, categories: selected, radius_m: Number($('radius').value), stop_count: Number($('stop-count').value), title: $('adventure-title').value.trim() || 'Dublin adventure'};
  }
  const metres = value => value >= 1000 ? `${(value / 1000).toFixed(2)} km` : `${Math.round(value)} m`;
  function icon(text, category = '', visited = false) {
    // Only fixed labels, category codes and server-generated integers enter HTML.
    return L.divIcon({className: `quest-pin ${category} ${visited ? 'visited-pin' : ''}`, html: `<span>${text}</span>`, iconSize: [34, 34], iconAnchor: [17, 17]});
  }
  function popup(feature, title) {
    const content = node('div');
    content.append(node('strong', title || feature.properties.name), node('span', labels[feature.properties.category] || 'Park boundary'));
    if (feature.properties.category === 'park') content.append(node('p', 'Representative point, not a verified entrance.'));
    return content;
  }
  function drawStart() {
    if (startMarker) map.removeLayer(startMarker);
    if (radiusLayer) map.removeLayer(radiusLayer);
    startMarker = radiusLayer = null;
    if (!state.start) return;
    const point = [state.start.lat, state.start.lng];
    startMarker = L.marker(point, {icon: icon('S', 'start-pin'), title: 'Starting location', alt: 'Starting location', keyboard: true}).addTo(map).bindPopup(node('strong', state.start.name));
    radiusLayer = L.circle(point, {radius: Number($('radius').value), color: '#58774b', weight: 1.5, dashArray: '5 6', fillOpacity: .045}).addTo(map);
  }
  function clearSpatial() {
    spatialLayer.clearLayers();
    $('spatial-section').hidden = true;
    $('spatial-list').replaceChildren();
  }
  function chooseStart(lat, lng, name, pan = true) {
    state.start = {lat, lng, name};
    $('start-label').textContent = `${name} · ${lat.toFixed(5)}, ${lng.toFixed(5)}`;
    $('clear-start').hidden = false;
    clearSpatial();
    drawStart();
    updateStartControls();
    if (pan) map.setView([lat, lng], 15);
    tell(state.adventure ? 'Builder start updated. Generate a new adventure or regenerate the current one to apply it.' : 'Starting point selected. Choose your interests and generate an adventure.');
  }
  function fitResults() {
    const bounds = L.featureGroup([adventureLayer, spatialLayer, walkingLayer]).getBounds();
    if (startMarker) bounds.extend(startMarker.getLatLng());
    if (bounds.isValid()) map.fitBounds(bounds.pad(.15), {maxZoom: 16});
    else map.setView([53.3498, -6.2603], 13);
  }
  function sourceDetails(feature) {
    const details = node('details');
    details.append(node('summary', 'Data source & attribution'));
    const source = feature.properties.source;
    if (source) {
      details.append(node('p', `${source.title} — ${source.publisher}. ${source.attribution} Licence: ${source.licence_name}.`, 'source-note'));
      // Only permit absolute HTTP(S) source URLs; never javascript: URLs.
      try {
        const url = new URL(source.resource_url);
        if (['https:', 'http:'].includes(url.protocol)) {
          const link = node('a', 'View original dataset');
          link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
          details.append(link);
        }
      } catch { /* Attribution text remains available for a malformed source URL. */ }
    } else details.append(node('p', 'Created by DublinQuest staff; not attributed to an imported dataset.', 'source-note'));
    return details;
  }
  function focusStop(stop) {
    const marker = stopMarkers.get(stop.id);
    if (!marker) return;
    map.setView(marker.getLatLng(), 17);
    marker.openPopup();
    $('map').scrollIntoView({block: 'center'});
  }
  function renderAdventure(adventure, fit = true, focus = false) {
    const geometryKey = JSON.stringify([adventure.id, adventure.path, adventure.stops.map(stop => stop.id)]);
    if (state.geometryKey !== geometryKey) clearWalking();
    state.geometryKey = geometryKey;
    state.adventure = adventure;
    adventureLayer.clearLayers();
    stopMarkers.clear();
    clearSpatial();
    const [lng, lat] = adventure.start.coordinates;
    chooseStart(lat, lng, 'Saved adventure start', false);
    $('adventure-title').value = adventure.title;
    $('radius').value = String(adventure.radius_m);
    // API supports any integer radius; preserve values from non-UI clients.
    if (!$('radius').value) {
      const option = node('option', metres(adventure.radius_m));
      option.value = adventure.radius_m; $('radius').append(option); $('radius').value = option.value;
    }
    $('stop-count').value = adventure.requested_stops;
    document.querySelectorAll('[name="category"]').forEach(input => { input.checked = adventure.categories.includes(input.value); });
    drawStart();
    L.geoJSON(adventure.path, {style: {color: '#204a3b', weight: 3, dashArray: '7 7', opacity: .8}}).addTo(adventureLayer);
    // Use the actual server buffer, rather than treating a browser circle as a spatial query.
    if (radiusLayer) map.removeLayer(radiusLayer);
    radiusLayer = L.geoJSON(adventure.search_area, {style: {color: '#58774b', weight: 1.5, dashArray: '5 6', fillOpacity: .045}}).addTo(map);
    $('adventure-heading').textContent = adventure.title;
    $('sequence-notice').textContent = adventure.sequence_notice;
    $('distance-summary').textContent = `${metres(adventure.total_distance_m)} of straight-line connections`;
    $('adventure-warnings').textContent = adventure.warnings.join(' ');
    $('adventure-warnings').hidden = !adventure.warnings.length;
    $('progress-label').textContent = `${adventure.progress.visited} of ${adventure.progress.total} visited · ${adventure.progress.percent}%`;
    $('adventure-progress').value = adventure.progress.percent;
    $('completion').hidden = !adventure.progress.complete;
    const list = $('stop-list'); list.replaceChildren();
    for (const stop of adventure.stops) {
      const feature = stop.place, properties = feature.properties;
      const [stopLng, stopLat] = feature.geometry.coordinates;
      const marker = L.marker([stopLat, stopLng], {icon: icon(stop.position, properties.category, stop.visited), title: `${stop.position}. ${properties.name}`, alt: `Stop ${stop.position}: ${properties.name}`}).addTo(adventureLayer).bindPopup(popup(feature, `${stop.position}. ${properties.name}`));
      stopMarkers.set(stop.id, marker);
      const card = node('li', undefined, `stop-card${stop.visited ? ' visited' : ''}`);
      card.dataset.stopId = stop.id;
      card.append(node('span', String(stop.position), 'stop-number'));
      const content = node('div');
      content.append(node('span', labels[properties.category], `category-badge ${properties.category}`), node('h3', properties.name), node('p', properties.description || 'No description supplied by the source dataset.'));
      if (properties.artist) content.append(node('p', `Artist: ${properties.artist}`));
      if (properties.category === 'park') content.append(node('p', 'Representative point within the park; not a verified entrance.'));
      content.append(node('p', `${metres(stop.distance_from_start_m)} from start · ${metres(stop.distance_from_previous_m)} from previous stop (straight line)`));
      const controls = node('div', undefined, 'stop-controls');
      const label = node('label', undefined, 'visit-toggle');
      const checkbox = node('input'); checkbox.type = 'checkbox'; checkbox.checked = stop.visited;
      checkbox.setAttribute('aria-label', `Mark ${properties.name} as visited`);
      checkbox.addEventListener('change', () => {
        if (state.busy) { checkbox.checked = stop.visited; return; }
        const visited = checkbox.checked;
        run('Saving your progress…', async () => {
          let updated;
          try { updated = await api(`/api/adventures/${adventure.id}/stops/${stop.id}/`, 'PATCH', {visited}); }
          catch (error) { checkbox.checked = stop.visited; throw error; }
          renderAdventure(updated, false);
          const replacement = document.querySelector(`[data-stop-id="${stop.id}"] input`);
          if (replacement) replacement.focus({preventScroll: true});
          tell(updated.progress.complete ? 'Adventure complete! All stops are marked visited.' : 'Progress saved.');
          await refreshSaved();
        });
      });
      label.append(checkbox, node('span', 'Visited'));
      controls.append(label, button('Show on map', () => focusStop(stop)));
      content.append(controls, sourceDetails(feature)); card.append(content); list.append(card);
    }
    $('adventure-section').hidden = false; $('welcome').hidden = true;
    drawWalking();
    if (fit) fitResults();
    if (focus) $('adventure-heading').focus({preventScroll: false});
  }
  function clearWalking() {
    state.walking = null; state.walkingVisible = false;
    if (walkingLayer) walkingLayer.clearLayers();
    $('walking-summary').hidden = true;
    $('walking-route').textContent = 'Show walking route';
  }
  function drawWalking() {
    walkingLayer.clearLayers();
    const route = state.walking;
    $('walking-summary').hidden = !route || !state.walkingVisible;
    $('walking-route').textContent = state.walkingVisible ? 'Hide walking route' : 'Show walking route';
    if (!route || !state.walkingVisible) return;
    L.geoJSON(route.route, {style: {color: '#2267bd', weight: 5, opacity: .85}}).addTo(walkingLayer);
    $('walking-metrics').textContent = `${metres(route.distance_m)} estimated walking distance · ${(route.duration_s / 60).toFixed(1)} minutes walking`;
    $('walking-notice').textContent = route.notice;
    const maxSnap = Math.max(...route.waypoints.map(point => point.displacement_m));
    $('walking-snapping').textContent = `Solid blue line: mapped pedestrian route. Maximum waypoint adjustment: ${maxSnap.toFixed(1)} m. Attraction markers have not moved; adjusted positions are not verified entrances.`;
    $('walking-warning').textContent = route.warnings.join(' ');
  }
  async function refreshSaved(append = false) {
    const data = await api(append ? state.savedNext : '/api/adventures/');
    const list = $('saved-list');
    if (!append) list.replaceChildren();
    if (!data.count) list.append(node('p', 'Your next discovery starts above. Generate an adventure to save it here.', 'hint'));
    for (const adventure of data.results) {
      const card = node('article', undefined, 'saved-card');
      card.append(node('h3', adventure.title), node('p', `${adventure.progress.visited}/${adventure.progress.total} visited · ${metres(adventure.radius_m)} radius`), button('Open adventure', () => run('Opening saved adventure…', async () => {
        const saved = await api(`/api/adventures/${adventure.id}/`);
        renderAdventure(saved, true, true); tell('Saved adventure opened.');
      }), 'btn btn-outline-dark'));
      list.append(card);
    }
    state.savedNext = data.next; $('more-saved').hidden = !data.next;
  }
  async function searchPlaces(event) {
    event.preventDefault();
    const search = $('place-search').value.trim();
    if (!search) { tell('Enter a place name to search.', true); return; }
    await run('Searching Dublin places…', async () => {
      const data = await api(`/api/places/?search=${encodeURIComponent(search)}&page_size=20`);
      const results = $('search-results'); results.replaceChildren();
      for (const feature of data.features) {
        const choice = button(feature.properties.name, () => {
          const [lng, lat] = feature.geometry.coordinates;
          chooseStart(lat, lng, feature.properties.name);
          results.replaceChildren(); $('generate').focus();
        }, 'search-choice');
        choice.append(node('small', `${labels[feature.properties.category]}${feature.properties.category === 'park' ? ' · not a verified entrance' : ''}`));
        results.append(choice);
      }
      tell(data.count ? `${data.count} matching places. ${data.count > 20 ? 'Showing the first 20; refine your search for more specific results.' : 'Choose one as your start.'}` : 'No matching places. Try a shorter name or click the map.');
    });
  }
  async function allFeatures(url) {
    const features = []; let first;
    while (url) {
      const page = await api(url);
      first = first || page; features.push(...page.features); url = page.next;
    }
    return {...first, features};
  }
  function showSpatial(data, heading, summary, parks = false) {
    clearSpatial();
    $('spatial-heading').textContent = heading;
    $('spatial-summary').textContent = summary;
    for (const feature of data.features) {
      const layer = L.geoJSON(feature, parks ? {style: {color: '#287644', weight: 2, fillOpacity: .16}} : {
        pointToLayer: (_feature, latlng) => L.circleMarker(latlng, {radius: 7, color: '#fff', weight: 2, fillColor: '#823d77', fillOpacity: 1})
      }).addTo(spatialLayer);
      layer.bindPopup(popup(feature));
      const card = node('article', undefined, 'spatial-card');
      card.append(node('h3', feature.properties.name));
      if (parks) card.append(button('Find places inside this park', () => insidePark(feature), 'btn btn-outline-dark'));
      else {
        card.append(node('p', `${labels[feature.properties.category]}${feature.properties.distance_m !== null ? ' · ' + metres(feature.properties.distance_m) + ' from start' : ''}`));
        card.append(button('Use as starting point', () => {
          const [lng, lat] = feature.geometry.coordinates; chooseStart(lat, lng, feature.properties.name);
        }));
      }
      card.append(sourceDetails(feature)); $('spatial-list').append(card);
    }
    if (data.search_area) {
      if (radiusLayer) map.removeLayer(radiusLayer);
      radiusLayer = L.geoJSON(data.search_area, {style: {color: '#58774b', weight: 1.5, fillOpacity: .04}}).addTo(map);
    }
    $('spatial-section').hidden = false;
    if (!data.features.length) $('spatial-list').append(node('p', 'No matching locations found. Try a different radius, category or park.'));
    fitResults(); $('spatial-heading').focus(); tell(summary);
  }
  function queryString() {
    const values = criteria();
    return new URLSearchParams({lat: values.lat, lng: values.lng, radius_m: values.radius_m});
  }
  function insidePark(feature) {
    run('Finding places inside the park boundary…', async () => {
      const selected = categories().filter(value => value !== 'park');
      if (!selected.length) throw new Error('Select at least one non-park category to find places inside a park.');
      const data = await allFeatures(`/api/parks/${feature.id}/places/?categories=${selected.join(',')}&page_size=100`);
      showSpatial(data, `Inside ${feature.properties.name}`, `${data.count} places covered by this park boundary (including its edge).`);
      L.geoJSON(feature, {style: {color: '#287644', fillOpacity: .1}}).addTo(spatialLayer);
      fitResults();
    });
  }
  function setup() {
    map = L.map('map', {scrollWheelZoom: false}).setView([53.3498, -6.2603], 13);
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(map);
    let tileWarning = false;
    tiles.on('tileerror', () => {
      if (!tileWarning) { tileWarning = true; tell('Some map tiles could not load. Check your internet connection. Place search and adventure controls remain available.', true); }
    });
    adventureLayer = L.featureGroup().addTo(map); spatialLayer = L.featureGroup().addTo(map); walkingLayer = L.featureGroup().addTo(map);
    L.control.scale({imperial: false}).addTo(map);
    map.on('click', event => { if (!state.busy) chooseStart(event.latlng.lat, event.latlng.lng, 'Map selection', false); });
    $('place-search-form').addEventListener('submit', searchPlaces);
    $('clear-start').addEventListener('click', () => {
      state.start = null; $('start-label').textContent = 'No location selected'; $('clear-start').hidden = true; drawStart(); clearSpatial(); updateStartControls(); tell('Choose a new starting point. Saved adventures are unchanged.');
    });
    $('radius').addEventListener('change', () => { drawStart(); clearSpatial(); tell('Radius updated for your next search or generation.'); });
    $('fit-map').addEventListener('click', fitResults);
    $('clear-spatial').addEventListener('click', clearSpatial);
    $('adventure-form').addEventListener('submit', event => {
      event.preventDefault();
      // Capture values before the loading state temporarily disables inputs.
      let values; try { values = criteria(); } catch (error) { tell(error.message, true); return; }
      run('Finding your next Dublin discoveries…', async () => {
        const adventure = await api('/api/adventures/', 'POST', values);
        renderAdventure(adventure, true, true);
        tell(adventure.warnings.length ? adventure.warnings.join(' ') : 'Your adventure is ready and saved. Let curiosity lead the way.');
        await refreshSaved();
      });
    });
    $('refresh-saved').addEventListener('click', () => run('Loading saved adventures…', async () => { await refreshSaved(); tell('Saved adventures refreshed.'); }));
    $('more-saved').addEventListener('click', () => run('Loading more adventures…', async () => { await refreshSaved(true); tell('More adventures loaded.'); }));
    $('walking-route').addEventListener('click', () => {
      if (!state.adventure || state.busy) return;
      if (state.walking) {
        state.walkingVisible = !state.walkingVisible; drawWalking();
        tell(state.walkingVisible ? 'Walking route shown from this page’s saved result.' : 'Walking route hidden. Showing the straight-line sequence.');
        return;
      }
      run('Requesting an optional walking route…', async () => {
        const route = await api(`/api/adventures/${state.adventure.id}/walking-route/`, 'POST', {});
        if (route.status !== 'available') { tell(route.detail); return; }
        state.walking = route; state.walkingVisible = true; drawWalking(); fitResults();
        tell('Walking route displayed. Times are estimates and exclude visits; check access yourself.');
      });
    });
    $('regenerate').addEventListener('click', () => {
      if (!state.adventure) return;
      if (!window.confirm('Replace the stops using the current builder settings? This resets all visited progress.')) return;
      let values; try { values = criteria(); } catch (error) { tell(error.message, true); return; }
      run('Regenerating your adventure…', async () => {
        const adventure = await api(`/api/adventures/${state.adventure.id}/regenerate/`, 'POST', {...values, confirm_reset: true});
        renderAdventure(adventure, true, true); tell(adventure.warnings.join(' ') || 'Adventure regenerated. Visited progress has been reset.'); await refreshSaved();
      });
    });
    $('rename').addEventListener('click', () => {
      const title = window.prompt('Adventure name', state.adventure.title);
      if (title === null) return;
      run('Saving adventure name…', async () => {
        renderAdventure(await api(`/api/adventures/${state.adventure.id}/`, 'PATCH', {title: title.trim()}), false);
        tell('Adventure renamed.'); await refreshSaved();
      });
    });
    $('delete-adventure').addEventListener('click', () => {
      if (!window.confirm('Delete this saved adventure? This cannot be undone.')) return;
      run('Deleting adventure…', async () => {
        await api(`/api/adventures/${state.adventure.id}/`, 'DELETE');
        state.adventure = null; clearWalking(); state.geometryKey = null; adventureLayer.clearLayers(); stopMarkers.clear(); $('adventure-section').hidden = true; $('welcome').hidden = false;
        tell('Adventure deleted. Your imported places and parks are unchanged.'); await refreshSaved(); $('saved-heading').scrollIntoView({block: 'center'});
      });
    });
    $('nearby').addEventListener('click', () => run('Searching nearby places…', async () => {
      const params = queryString(); params.set('categories', categories().join(',')); params.set('page_size', 100);
      const data = await allFeatures(`/api/places/nearby/?${params}`);
      showSpatial(data, 'Nearby places', `${data.count} places within ${metres(Number($('radius').value))} of your selected start.`);
    }));
    $('intersections').addEventListener('click', () => run('Finding intersecting park boundaries…', async () => {
      const params = queryString(); params.set('page_size', 100);
      const data = await allFeatures(`/api/parks/intersecting/?${params}`);
      showSpatial(data, 'Parks overlapping your radius', `${data.count} park boundaries intersect the search area. Categories do not apply to this park-boundary query.`, true);
    }));
    $('park-search-form').addEventListener('submit', event => {
      event.preventDefault(); const search = $('park-search').value.trim();
      if (!search) { tell('Enter a park name.', true); return; }
      run('Finding parks…', async () => {
        const data = await api(`/api/parks/?search=${encodeURIComponent(search)}&page_size=20`);
        const results = $('park-results'); results.replaceChildren();
        for (const feature of data.features) results.append(button(`Inside ${feature.properties.name}`, () => insidePark(feature), 'search-choice'));
        tell(data.count ? `Choose a park to find places within its boundary.${data.count > 20 ? ' Showing the first 20; refine your search.' : ''}` : 'No matching parks. Try a shorter name.');
      });
    });
    run('Preparing your guest session…', async () => {
      state.csrf = (await api('/api/session/')).csrfToken;
      await refreshSaved(); tell('Choose a starting point on the map or search for a place.');
    });
  }
  try { setup(); }
  catch { tell('The map could not start. Reload the page; if this continues, check that the application static files are available.', true); }
})();
