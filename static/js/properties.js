/* =============================================================
   Larney Properties – Fetch-based property loader
   Fetches /api/properties, hides skeleton grid, injects cards.
   Requires window.LP_QUERY and window.LP_IS_AGENT to be set
   by the Jinja2 template before this script loads.
   ============================================================= */

'use strict';

// ── DOM refs ──────────────────────────────────────────────────
const SKEL         = document.getElementById('skeletonGrid');
const GRID         = document.getElementById('propertyGrid');
const EMPTY_STATE  = document.getElementById('emptyState');
const EMPTY_FILTER = document.getElementById('emptyFilter');
const COUNT        = document.getElementById('resultsCount');

// ── Filter state ──────────────────────────────────────────────
let activeStatus = 'all';
let activeType   = 'all';

// ── Favourites key ────────────────────────────────────────────
const FAVES_KEY = 'lp_favourites';

function getFaves() {
  return new Set(JSON.parse(localStorage.getItem(FAVES_KEY) || '[]'));
}

// ── XSS-safe HTML escaping ────────────────────────────────────
function escHtml(str) {
  return String(str == null ? '' : str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
}

// ── Price formatter (mirrors Flask format_price filter) ───────
function formatPrice(val) {
  const digits = String(val || '').replace(/\D/g, '');
  if (!digits) return escHtml(String(val || ''));
  // Space-separated thousands (SA convention)
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
}

// ── Build a single property card HTML string ──────────────────
function buildCard(p) {
  const status  = p.status        || 'For Sale';
  const ptype   = p.property_type || 'House';
  const faves   = getFaves();
  const isFaved = faves.has(String(p.id));

  // Property image or placeholder
  const imgHtml = p.image_filename
    ? `<img src="/static/uploads/${escHtml(p.image_filename)}"
            alt="${escHtml(p.title)}" class="lp-card-img" loading="lazy" />`
    : `<div class="lp-card-img-placeholder">
         <i class="bi bi-house-fill fs-1 opacity-25" style="color:var(--lp-navy);"></i>
       </div>`;

  const ribbonHtml = p.is_featured
    ? `<div class="lp-featured-ribbon">Featured</div>` : '';

  // Specs row (only rendered if at least one value exists)
  const specsHtml = (p.bedrooms || p.bathrooms || p.size_sqm) ? `
    <div class="lp-specs d-flex gap-3 flex-wrap mb-3">
      ${p.bedrooms  ? `<span class="lp-spec-item"><i class="bi bi-door-open-fill"></i>${p.bedrooms} Bed${p.bedrooms !== 1 ? 's' : ''}</span>` : ''}
      ${p.bathrooms ? `<span class="lp-spec-item"><i class="bi bi-droplet-fill"></i>${p.bathrooms} Bath${p.bathrooms !== 1 ? 's' : ''}</span>` : ''}
      ${p.size_sqm  ? `<span class="lp-spec-item"><i class="bi bi-arrows-fullscreen"></i>${p.size_sqm} m²</span>` : ''}
    </div>` : '';

  const desc = p.description || '';
  const descHtml = desc
    ? `<p class="card-text small text-muted flex-grow-1 mb-3">${escHtml(
        desc.length > 80 ? desc.substring(0, 80) + '\u2026' : desc
      )}</p>` : '';

  // Agent footer (view + edit + delete) vs public footer (view only)
  // JSON.stringify safely encodes the confirm message for the onsubmit attribute
  const confirmMsg = JSON.stringify(`Delete ${p.title}?`);
  const footerHtml = window.LP_IS_AGENT
    ? `<div class="d-flex gap-2">
         <a href="/property/${p.id}" class="btn lp-btn-primary btn-sm flex-grow-1">
           <i class="bi bi-eye me-1"></i>View
         </a>
         <a href="/property/${p.id}/edit" class="btn btn-outline-warning btn-sm px-3" title="Edit">
           <i class="bi bi-pencil-fill"></i>
         </a>
         <form method="POST" action="/property/${p.id}/delete" class="d-inline"
               onsubmit="return confirm(${escHtml(confirmMsg)})">
           <button type="submit" class="btn btn-outline-danger btn-sm px-3" title="Delete">
             <i class="bi bi-trash-fill"></i>
           </button>
         </form>
       </div>`
    : `<a href="/property/${p.id}" class="btn lp-btn-primary w-100 btn-sm">
         <i class="bi bi-eye me-1"></i>View Details
       </a>`;

  return `
    <div class="col-12 col-sm-6 col-xl-4 property-card-col"
         data-status="${escHtml(status)}"
         data-type="${escHtml(ptype)}">
      <div class="card lp-card shadow-sm h-100">
        <div class="lp-card-img-wrap">
          ${imgHtml}
          <span class="position-absolute top-0 start-0 m-2 lp-badge-status
                       ${status === 'For Sale' ? 'lp-badge-sale' : 'lp-badge-let'}">
            ${escHtml(status)}
          </span>
          <span class="position-absolute bottom-0 start-0 m-2 lp-badge-type">
            ${escHtml(ptype)}
          </span>
          ${ribbonHtml}
          <button class="lp-fav-btn ${isFaved ? 'saved' : ''}"
                  data-prop-id="${p.id}"
                  title="Save to favourites" aria-label="Save to favourites">
            <i class="bi bi-heart-fill"></i>
          </button>
        </div>
        <div class="card-body d-flex flex-column p-3">
          <div class="lp-price mb-1">R\u00a0${formatPrice(p.price)}</div>
          <h5 class="card-title fw-semibold mb-1 fs-6">${escHtml(p.title)}</h5>
          <p class="text-muted small mb-2">
            <i class="bi bi-geo-alt-fill lp-icon-accent me-1"></i>${escHtml(p.location)}
          </p>
          ${descHtml}
          ${specsHtml}
        </div>
        <div class="card-footer bg-transparent border-0 pb-3 px-3">
          ${footerHtml}
        </div>
      </div>
    </div>`;
}

// ── Fetch properties from Flask JSON route ────────────────────
async function loadProperties() {
  const query = window.LP_QUERY || '';
  const url   = `/api/properties${query ? '?q=' + encodeURIComponent(query) : ''}`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Hide skeleton regardless of result
    if (SKEL) SKEL.classList.add('lp-hidden');

    const props = data.properties || [];

    if (props.length === 0) {
      // Show API-level empty state (no properties or no search hits)
      if (EMPTY_STATE) {
        const msgEl = document.getElementById('emptyStateMsg');
        if (msgEl) {
          msgEl.innerHTML = query
            ? `No properties found for <strong>&ldquo;${escHtml(query)}&rdquo;</strong>.`
            : 'No properties listed yet.';
        }
        EMPTY_STATE.classList.remove('d-none');
      }
      if (COUNT) COUNT.textContent = '0 properties';
      return;
    }

    // Inject cards into the real grid
    if (GRID) {
      GRID.innerHTML = props.map(buildCard).join('');
      GRID.classList.remove('lp-hidden');
    }

    const n = props.length;
    if (COUNT) COUNT.textContent = `${n} propert${n === 1 ? 'y' : 'ies'}`;

    attachFavButtons();
    staggerCards();

  } catch (err) {
    console.error('[LP] Property fetch failed:', err);
    if (SKEL) SKEL.classList.add('lp-hidden');
    if (GRID) {
      GRID.innerHTML = `
        <div class="col-12 text-center py-5">
          <i class="bi bi-wifi-off fs-1 text-muted"></i>
          <p class="mt-3 text-muted">Could not load listings. Please refresh the page.</p>
        </div>`;
      GRID.classList.remove('lp-hidden');
    }
  }
}

// ── Wire up favourite heart buttons (called after each render) ─
function attachFavButtons() {
  document.querySelectorAll('.lp-fav-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.preventDefault();
      e.stopPropagation();
      const id    = btn.dataset.propId;
      const faves = getFaves();
      if (faves.has(id)) { faves.delete(id); } else { faves.add(id); }
      localStorage.setItem(FAVES_KEY, JSON.stringify([...faves]));
      btn.classList.toggle('saved', faves.has(id));
    });
  });
}

// ── Stagger fade-in animation on freshly rendered cards ───────
function staggerCards() {
  document.querySelectorAll('.property-card-col').forEach((card, i) => {
    card.style.opacity    = '0';
    card.style.animation  = `fadeUp 0.45s ease ${i * 0.07}s forwards`;
  });
}

// ── Client-side filter (status & type pills) ──────────────────
function applyFilters() {
  const cards = document.querySelectorAll('.property-card-col');
  if (!cards.length) return; // grid not populated yet

  let visible = 0;
  cards.forEach(card => {
    const ok = (activeStatus === 'all' || card.dataset.status === activeStatus)
            && (activeType   === 'all' || card.dataset.type   === activeType);
    card.style.display = ok ? '' : 'none';
    if (ok) visible++;
  });

  if (EMPTY_FILTER) EMPTY_FILTER.classList.toggle('d-none', visible > 0);
  if (COUNT)        COUNT.textContent = `${visible} propert${visible === 1 ? 'y' : 'ies'}`;
}

// Exposed globally so the "Clear Filters" button onclick can call it
function resetFilters() {
  document.querySelectorAll('.lp-pill').forEach(p => {
    p.classList.toggle('active', p.dataset.filterVal === 'all');
  });
  activeStatus = 'all';
  activeType   = 'all';
  applyFilters();
}

document.querySelectorAll('.lp-pill').forEach(pill => {
  pill.addEventListener('click', () => {
    const group = pill.dataset.filterGroup;
    const val   = pill.dataset.filterVal;

    document.querySelectorAll(`.lp-pill[data-filter-group="${group}"]`)
            .forEach(p => p.classList.remove('active'));
    pill.classList.add('active');

    if (group === 'status') activeStatus = val;
    if (group === 'type')   activeType   = val;

    applyFilters();
  });
});

// ── Kick everything off ───────────────────────────────────────
loadProperties();
