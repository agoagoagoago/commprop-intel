/**
 * CommProp Intel Map - Frontend JavaScript
 * Interactive map and data visualization for Singapore commercial properties
 */

// State
let map = null;
let markerCluster = null;
let allListings = [];
let filteredListings = [];
let advertisers = [];
let typeChart = null;
let ownerAgentChart = null;

// Filter state
let filters = {
    advertiserType: 'all', // all, owner, agent
    propertyTypes: ['Factory/Warehouse', 'Office', 'Shop', 'Other', 'Mixed', null],
    transactionTypes: ['Sale', 'Rent', 'Both', null],
    minPrice: null,
    maxPrice: null,
    dateRangeDays: 30  // 7, 30, or 'all'
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    loadData();
});

/**
 * Initialize Leaflet map centered on Singapore
 */
function initMap() {
    // Singapore coordinates and bounds
    const singapore = [1.3521, 103.8198];

    // Singapore boundary box - restrict map to Singapore only
    const singaporeBounds = L.latLngBounds(
        [1.1500, 103.6000],  // Southwest corner
        [1.4700, 104.1000]   // Northeast corner
    );

    map = L.map('map', {
        center: singapore,
        zoom: 11,
        minZoom: 10,
        maxZoom: 18,
        zoomControl: true,
        attributionControl: true,
        maxBounds: singaporeBounds,
        maxBoundsViscosity: 1.0  // Prevent panning outside bounds
    });

    // Dark tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 18,
        bounds: singaporeBounds
    }).addTo(map);

    // Initialize marker cluster group
    markerCluster = L.markerClusterGroup({
        chunkedLoading: true,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        maxClusterRadius: 50,
        iconCreateFunction: function (cluster) {
            const count = cluster.getChildCount();
            let size = 'small';
            if (count > 10) size = 'medium';
            if (count > 50) size = 'large';

            return L.divIcon({
                html: `<div class="cluster-icon cluster-${size}">${count}</div>`,
                className: 'marker-cluster',
                iconSize: L.point(40, 40)
            });
        }
    });

    map.addLayer(markerCluster);

    // Add custom cluster styles
    addClusterStyles();
}

/**
 * Add CSS for marker clusters
 */
function addClusterStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .marker-cluster {
            background: transparent;
        }
        .cluster-icon {
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            font-weight: 700;
            font-size: 14px;
            color: white;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .cluster-small {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
        }
        .cluster-medium {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%);
            font-size: 15px;
        }
        .cluster-large {
            width: 52px;
            height: 52px;
            background: linear-gradient(135deg, #ec4899 0%, #db2777 100%);
            font-size: 16px;
        }
    `;
    document.head.appendChild(style);
}

/**
 * Load all data from API
 */
async function loadData() {
    showLoading('Loading listings...');

    try {
        // Load listings and advertisers in parallel
        const [listingsRes, advertisersRes, summaryRes] = await Promise.all([
            fetch('/api/listings'),
            fetch('/api/analytics/advertisers'),
            fetch('/api/analytics/summary')
        ]);

        if (listingsRes.ok) {
            allListings = await listingsRes.json();
            applyFilters();
        }

        if (advertisersRes.ok) {
            advertisers = await advertisersRes.json();
            renderAdvertisersList();
        }

        if (summaryRes.ok) {
            const summary = await summaryRes.json();
            updateHeaderStats(summary);
        }

        // Load analytics for charts
        loadAnalytics();

    } catch (error) {
        console.error('Error loading data:', error);
    } finally {
        hideLoading();
    }
}

/**
 * Load analytics data for charts
 */
async function loadAnalytics() {
    try {
        const res = await fetch('/api/analytics/trends');
        if (res.ok) {
            const data = await res.json();
            renderCharts(data);
        }
    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}

/**
 * Update header statistics
 */
function updateHeaderStats(summary) {
    document.getElementById('totalListings').textContent = summary.total_listings || 0;
    document.getElementById('ownerListings').textContent = summary.owner_listings || 0;
    document.getElementById('onMapCount').textContent = summary.with_coordinates || 0;
}

/**
 * Apply current filters and update map
 */
function applyFilters() {
    // Get selected property types
    const propertyTypesSelected = [];
    if (document.getElementById('typeFactory')?.checked) propertyTypesSelected.push('Factory/Warehouse');
    if (document.getElementById('typeOffice')?.checked) propertyTypesSelected.push('Office');
    if (document.getElementById('typeShop')?.checked) propertyTypesSelected.push('Shop');
    if (document.getElementById('typeOther')?.checked) {
        propertyTypesSelected.push('Other', 'Mixed', null);
    }
    filters.propertyTypes = propertyTypesSelected;

    // Get transaction types
    const transTypesSelected = [];
    if (document.getElementById('transSale')?.checked) transTypesSelected.push('Sale', 'Both');
    if (document.getElementById('transRent')?.checked) transTypesSelected.push('Rent', 'Both');
    if (transTypesSelected.length === 0) transTypesSelected.push(null);
    filters.transactionTypes = transTypesSelected;

    // Get price range
    filters.minPrice = parseInt(document.getElementById('minPrice')?.value) || null;
    filters.maxPrice = parseInt(document.getElementById('maxPrice')?.value) || null;

    // Calculate cutoff date for date range filter
    let cutoffDate = null;
    if (filters.dateRangeDays !== 'all' && typeof filters.dateRangeDays === 'number') {
        const today = new Date();
        cutoffDate = new Date(today.setDate(today.getDate() - filters.dateRangeDays));
    }

    // Filter listings
    filteredListings = allListings.filter(listing => {
        // Date range filter
        if (cutoffDate && listing.first_seen_date) {
            const listingDate = new Date(listing.first_seen_date);
            if (listingDate < cutoffDate) return false;
        }

        // Advertiser type filter
        if (filters.advertiserType === 'owner' && !listing.is_owner) return false;
        if (filters.advertiserType === 'agent' && !listing.is_agent) return false;

        // Property type filter
        if (!filters.propertyTypes.includes(listing.property_type)) return false;

        // Transaction type filter
        if (listing.transaction_type && !filters.transactionTypes.includes(listing.transaction_type)) {
            return false;
        }

        // Price filter
        if (filters.minPrice && listing.price && listing.price < filters.minPrice) return false;
        if (filters.maxPrice && listing.price && listing.price > filters.maxPrice) return false;

        return true;
    });

    renderMarkers();

    // Update filtered count in header
    document.getElementById('totalListings').textContent = filteredListings.length;
}

/**
 * Set date range filter
 */
function setDateRange(days) {
    filters.dateRangeDays = days;

    // Update button states
    document.querySelectorAll('.filter-buttons .filter-btn[data-range]').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.range == days) {
            btn.classList.add('active');
        }
    });

    applyFilters();
}

/**
 * Render markers on the map
 */
function renderMarkers() {
    // Clear existing markers
    markerCluster.clearLayers();

    // Filter listings with coordinates
    const mappableListings = filteredListings.filter(l => l.latitude && l.longitude);

    // Create markers
    mappableListings.forEach(listing => {
        const marker = createMarker(listing);
        if (marker) {
            markerCluster.addLayer(marker);
        }
    });

    // Update on-map count
    document.getElementById('onMapCount').textContent = mappableListings.length;
}

/**
 * Create a marker for a listing
 */
function createMarker(listing) {
    if (!listing.latitude || !listing.longitude) return null;

    // Determine marker color based on owner/agent status
    let color = '#6b7280'; // grey for unknown
    if (listing.is_owner) color = '#10b981'; // green for owner
    else if (listing.is_agent) color = '#3b82f6'; // blue for agent

    // Create custom icon
    const icon = L.divIcon({
        html: `<div style="
            background: ${color};
            width: 24px;
            height: 24px;
            border-radius: 50%;
            border: 3px solid white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        "></div>`,
        className: 'custom-marker',
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });

    const marker = L.marker([listing.latitude, listing.longitude], { icon });

    // Create popup content
    const popupContent = createPopupContent(listing);
    marker.bindPopup(popupContent, {
        maxWidth: 300,
        className: 'custom-popup'
    });

    // Show popup on hover instead of click
    marker.on('mouseover', function (e) {
        this.openPopup();
    });
    marker.on('mouseout', function (e) {
        // Small delay before closing to allow reading
        setTimeout(() => {
            if (!this.getPopup().getElement()?.matches(':hover')) {
                this.closePopup();
            }
        }, 300);
    });

    return marker;
}

/**
 * Create popup content for a listing
 */
function createPopupContent(listing) {
    const price = listing.price ? formatPrice(listing.price) : 'Price N/A';
    const sqft = listing.gfa_sqft ? `${listing.gfa_sqft.toLocaleString()} sqft` : '';
    const psf = (listing.price && listing.gfa_sqft)
        ? `$${Math.round(listing.price / listing.gfa_sqft).toLocaleString()} psf`
        : '';

    let typeLabel = '';
    if (listing.is_owner) typeLabel = '<span style="color: #10b981;">🟢 Owner</span>';
    else if (listing.is_agent) typeLabel = '<span style="color: #3b82f6;">🔵 Agent</span>';

    return `
        <div class="popup-content">
            <div class="popup-title">${listing.property_name || 'Property Listing'}</div>
            <div class="popup-price">${price}</div>
            <div class="popup-details">
                ${sqft ? `<div>${sqft} ${psf ? `• ${psf}` : ''}</div>` : ''}
                <div>${listing.property_type || ''} ${listing.transaction_type ? `• ${listing.transaction_type}` : ''}</div>
                ${typeLabel ? `<div>${typeLabel}</div>` : ''}
            </div>
            ${listing.contact_name || listing.contact_phone ? `
                <div class="popup-contact">
                    📞 ${listing.contact_name || ''} ${listing.contact_phone || ''}
                </div>
            ` : ''}
            <button class="popup-btn" onclick="showListingDetail('${listing.id}')">
                View Details
            </button>
        </div>
    `;
}

/**
 * Format price for display
 */
function formatPrice(price) {
    if (price >= 1000000) {
        return `$${(price / 1000000).toFixed(2)}M`;
    } else if (price >= 1000) {
        return `$${(price / 1000).toFixed(0)}K`;
    }
    return `$${price.toLocaleString()}`;
}

/**
 * Show listing detail in modal
 */
function showListingDetail(listingId) {
    const listing = allListings.find(l => l.id === listingId);
    if (!listing) return;

    const modal = document.getElementById('listingModal');
    const modalBody = document.getElementById('modalBody');

    const price = listing.price ? formatPrice(listing.price) : 'N/A';
    const sqft = listing.gfa_sqft ? `${listing.gfa_sqft.toLocaleString()} sqft` : 'N/A';
    const psf = (listing.price && listing.gfa_sqft)
        ? `$${Math.round(listing.price / listing.gfa_sqft).toLocaleString()}`
        : 'N/A';

    let badges = '';
    if (listing.is_owner) badges += '<span class="badge owner">Owner</span>';
    if (listing.is_agent) badges += '<span class="badge agent">Agent</span>';
    if (listing.transaction_type === 'Sale') badges += '<span class="badge sale">For Sale</span>';
    if (listing.transaction_type === 'Rent') badges += '<span class="badge rent">For Rent</span>';

    modalBody.innerHTML = `
        <div class="modal-header">
            <h2 class="modal-title">${listing.property_name || 'Property Listing'}</h2>
            <div class="modal-badges">${badges}</div>
        </div>
        
        <div class="modal-details">
            <div class="detail-item">
                <div class="detail-label">Price</div>
                <div class="detail-value">${price}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Floor Area</div>
                <div class="detail-value">${sqft}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Price per sqft</div>
                <div class="detail-value">${psf}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Property Type</div>
                <div class="detail-value">${listing.property_type || 'N/A'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Lease Type</div>
                <div class="detail-value">${listing.lease_type || 'N/A'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Contact</div>
                <div class="detail-value">${listing.contact_name || ''} ${listing.contact_phone || 'N/A'}</div>
            </div>
        </div>
        
        <div class="modal-raw-text">
            <h4>Original Listing</h4>
            ${listing.raw_text}
        </div>
    `;

    modal.classList.add('active');
}

/**
 * Close modal
 */
function closeModal() {
    document.getElementById('listingModal').classList.remove('active');
}

// Close modal on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// Close modal on backdrop click
document.getElementById('listingModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'listingModal') closeModal();
});

/**
 * Set advertiser type filter
 */
function setAdvertiserFilter(type) {
    filters.advertiserType = type;

    // Update button states
    document.querySelectorAll('.filter-buttons .filter-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.filter === type) {
            btn.classList.add('active');
        }
    });

    applyFilters();
}

/**
 * Toggle sidebar visibility
 */
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('collapsed');

    // Invalidate map size after transition
    setTimeout(() => {
        map.invalidateSize();
    }, 300);
}

/**
 * Render top advertisers list
 */
function renderAdvertisersList() {
    const container = document.getElementById('topAdvertisersList');
    if (!container) return;

    container.innerHTML = advertisers.slice(0, 10).map(adv => {
        let typeClass = '';
        let typeLabel = '';
        if (adv.is_owner) {
            typeClass = 'owner';
            typeLabel = 'Owner';
        } else if (adv.is_agent) {
            typeClass = 'agent';
            typeLabel = adv.agency_name || 'Agent';
        }

        return `
            <div class="advertiser-item">
                <div class="advertiser-info">
                    <span class="advertiser-name">${adv.name || 'Unknown'}</span>
                    <span class="advertiser-phone">${adv.phone}</span>
                    ${typeLabel ? `<span class="advertiser-type ${typeClass}">${typeLabel}</span>` : ''}
                </div>
                <span class="advertiser-count">${adv.total_listings}</span>
            </div>
        `;
    }).join('');
}

/**
 * Render analytics charts
 */
function renderCharts(data) {
    // Property type chart
    const typeCtx = document.getElementById('typeChart')?.getContext('2d');
    if (typeCtx) {
        if (typeChart) typeChart.destroy();

        const types = data.by_property_type || {};
        typeChart = new Chart(typeCtx, {
            type: 'doughnut',
            data: {
                labels: Object.keys(types),
                datasets: [{
                    data: Object.values(types),
                    backgroundColor: [
                        '#6366f1',
                        '#10b981',
                        '#f59e0b',
                        '#ef4444',
                        '#8b5cf6'
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#94a3b8',
                            font: { size: 11 }
                        }
                    }
                }
            }
        });
    }

    // Owner vs Agent chart
    const ownerCtx = document.getElementById('ownerAgentChart')?.getContext('2d');
    if (ownerCtx) {
        if (ownerAgentChart) ownerAgentChart.destroy();

        const oa = data.owner_vs_agent || {};
        ownerAgentChart = new Chart(ownerCtx, {
            type: 'bar',
            data: {
                labels: ['Owner', 'Agent', 'Unknown'],
                datasets: [{
                    data: [oa.owner || 0, oa.agent || 0, oa.unknown || 0],
                    backgroundColor: ['#10b981', '#3b82f6', '#6b7280'],
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { color: '#64748b' },
                        grid: { color: '#334155' }
                    },
                    x: {
                        ticks: { color: '#94a3b8' },
                        grid: { display: false }
                    }
                }
            }
        });
    }
}

/**
 * Trigger a scrape
 */
async function triggerScrape() {
    const btn = document.getElementById('scrapeBtn');
    btn.classList.add('loading');
    btn.innerHTML = '<span class="btn-icon">⏳</span><span>Fetching...</span>';

    showLoading('Scraping stclassifieds.sg...');

    try {
        const res = await fetch('/api/scrape', { method: 'POST' });
        const data = await res.json();

        if (data.status === 'completed') {
            showLoading(`Found ${data.listings_found} listings. ${data.new} new, ${data.updated} updated.`);
            await new Promise(r => setTimeout(r, 1500));

            // Reload data
            await loadData();
        } else {
            alert('Scrape failed: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Scrape error:', error);
        alert('Failed to scrape: ' + error.message);
    } finally {
        btn.classList.remove('loading');
        btn.innerHTML = '<span class="btn-icon">🔄</span><span>Fetch Latest</span>';
        hideLoading();
    }
}

/**
 * Show loading overlay
 */
function showLoading(text = 'Loading...') {
    const overlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');
    if (overlay) overlay.classList.add('active');
    if (loadingText) loadingText.textContent = text;
}

/**
 * Hide loading overlay
 */
function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.classList.remove('active');
}
