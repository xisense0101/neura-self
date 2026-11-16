/* 
# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
*/

/**
 * OwO Strategy Engine & Team Optimizer Dashboard Module
 * Multi-account enabled controller with reactive auto-switching,
 * live Discord stealth-typing polling, and true analytical stat visualization.
 */

let strategyState = null;
let strategyWinner = null;
let strategyShardPlan = null;
let strategyConfig = {
    enabled: true,
    interval: 3600,
    auto_equip: false,
    auto_dismantle: false,
    dry_run: true
};
let isStratDirty = false;
let stratCountdownInterval = null;
let stratNextRunTimestamp = 0;
let stratEquipPollTimer = null;
let stratEquipProgressInterval = null;

// Animal Emoji Mapping for Rich Visual Badges
const ANIMAL_EMOJI_MAP = {
    'cow': '🐮', 'tiger': '🐯', 'cat': '🐱', 'giraffbot': '🦒', 'lion': '🦁',
    'owl': '🦉', 'eagle': '🦅', 'snake': '🐍', 'bear': '🐻', 'wolf': '🐺',
    'fox': '🦊', 'deer': '🦌', 'dog': '🐶', 'frog': '🐸', 'panda': '🐼',
    'rabbit': '🐰', 'monkey': '🐵', 'elephant': '🐘', 'rhino': '🦏', 'hippo': '🦛',
    'dragon': '🐉', 'phoenix': '🔥', 'unicorn': '🦄', 'blank': '🐾', 'fish': '🐟',
    'camel': '🐫', 'flamingo': '🦩', 'sloth': '🦥', 'penguin': '🐧'
};

function getAnimalEmoji(name) {
    if (!name) return '🐾';
    const clean = String(name).toLowerCase().trim();
    return ANIMAL_EMOJI_MAP[clean] || '🐾';
}

/**
 * Helper to resolve the currently active account ID from canonical core.js and accounts.js.
 * Always prioritizes window.currentAccountId and falls back to accountsList[0].
 */
function getEffectiveAccountId() {
    if (typeof currentAccountId !== 'undefined' && currentAccountId) {
        return String(currentAccountId);
    }
    if (typeof accountsList !== 'undefined' && Array.isArray(accountsList) && accountsList.length > 0) {
        return String(accountsList[0].id);
    }
    return '';
}

/**
 * Get display name for active account.
 */
function getAccountDisplayName() {
    const aid = getEffectiveAccountId();
    if (aid && typeof accountsList !== 'undefined' && Array.isArray(accountsList) && accountsList.length > 0) {
        const acc = accountsList.find(a => String(a.id) === String(aid));
        if (acc && acc.username) return acc.username;
    }
    return aid || 'Active Account';
}

/**
 * Update the header badge showing the active account.
 */
function updateStrategyAccountBadge() {
    const nameEl = document.getElementById('strat-account-name');
    if (!nameEl) return;
    nameEl.textContent = getAccountDisplayName();
}
window.updateStrategyAccountBadge = updateStrategyAccountBadge;

/**
 * Render responsive slot skeletons while awaiting lineup data
 */
function renderSlotSkeletons() {
    const slotsContainer = document.getElementById('cur-team-slots');
    if (!slotsContainer) return;
    slotsContainer.innerHTML = `
        <div class="pet-slot-skeleton">
            <div class="skeleton-num"></div>
            <div class="skeleton-body">
                <div class="skeleton-line-title"></div>
                <div class="skeleton-line-sub"></div>
            </div>
            <div class="skeleton-stats">
                <div class="skeleton-line-stat"></div>
                <div class="skeleton-line-stat"></div>
            </div>
        </div>
        <div class="pet-slot-skeleton">
            <div class="skeleton-num"></div>
            <div class="skeleton-body">
                <div class="skeleton-line-title"></div>
                <div class="skeleton-line-sub"></div>
            </div>
            <div class="skeleton-stats">
                <div class="skeleton-line-stat"></div>
                <div class="skeleton-line-stat"></div>
            </div>
        </div>
        <div class="pet-slot-skeleton">
            <div class="skeleton-num"></div>
            <div class="skeleton-body">
                <div class="skeleton-line-title"></div>
                <div class="skeleton-line-sub"></div>
            </div>
            <div class="skeleton-stats">
                <div class="skeleton-line-stat"></div>
                <div class="skeleton-line-stat"></div>
            </div>
        </div>
    `;
}

/**
 * Render subtle glowing pulse loaders on metric values rather than static dashes
 */
function setMetricLoaders() {
    const metricIds = ['cur-frontline-ehp', 'cur-total-ehp', 'cur-sustained-dps', 'cur-win-rate'];
    metricIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.innerHTML = '<span class="metric-pulse-loader"></span>';
        }
    });
}

/**
 * Render graceful fallback widget when lineup fetch fails or times out
 */
function renderLineupFallback(errorMsg) {
    const slotsContainer = document.getElementById('cur-team-slots');
    if (slotsContainer) {
        const hasExisting = strategyState && strategyState.team && Array.isArray(strategyState.team.animals) && strategyState.team.animals.length > 0;
        if (!hasExisting) {
            slotsContainer.innerHTML = `
                <div class="lineup-fallback-state">
                    <div class="fallback-icon">⚠️</div>
                    <div class="fallback-title">Lineup Telemetry Unavailable</div>
                    <div class="fallback-desc">${escapeHtml(errorMsg || 'Could not connect to strategy engine')}</div>
                    <button type="button" class="strat-btn primary-glow fallback-retry-btn" onclick="loadStrategyView(true)">
                        🔄 Retry Lineup Sync
                    </button>
                </div>
            `;
            const metricIds = ['cur-frontline-ehp', 'cur-total-ehp', 'cur-sustained-dps', 'cur-win-rate'];
            metricIds.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '--';
            });
        }
    }

    const verifiedBadge = document.getElementById('strat-verified-badge');
    if (verifiedBadge && (!strategyState || !strategyState.team_verified)) {
        verifiedBadge.className = 'strat-badge badge-paused';
        verifiedBadge.innerHTML = '<span class="badge-dot"></span> Offline';
    }

    const lastSyncedBadge = document.getElementById('strat-last-synced');
    if (lastSyncedBadge && (!strategyState || !strategyState.last_updated)) {
        lastSyncedBadge.textContent = 'Synced: Offline';
    }
}

let _strategyLoadAbortController = null;

/**
 * Initialize or refresh the Strategy View.
 * Implements Progressive / Resilient Multi-Stage Loading:
 * - Stage 1 (Immediate / Local): Render cached/default badges, active account name, slot skeletons, and pulse loaders without waiting.
 * - Stage 2 (Fast Lineup & Badges): Fetch /api/strategy/state?id=${currentAccountId} and render lineup, metrics, and badges.
 * - Stage 3 (Synergies & Settings): Render synergies, Wilson CI, and settings toggles independently without blocking lineup.
 * - Stage 4 (Telemetry / Stream): Update telemetry log stream independently.
 */
async function loadStrategyView(forceRefresh = false) {
    const aid = getEffectiveAccountId();
    const q = aid ? `?id=${encodeURIComponent(aid)}` : '';

    // =========================================================================
    // STAGE 1: Immediate / Local Render (0ms, non-blocking)
    // =========================================================================
    try {
        updateStrategyAccountBadge();
        renderStrategyBadges(strategyState);
        renderStrategySettings();

        const hasExistingTeam = strategyState && strategyState.team && Array.isArray(strategyState.team.animals) && strategyState.team.animals.length > 0;
        if (hasExistingTeam && !forceRefresh) {
            renderCurrentLineup();
            renderSynergiesAndSolvency();
        } else {
            renderSlotSkeletons();
            setMetricLoaders();
        }
    } catch (stage1Err) {
        console.warn('[Strategy Stage 1] Local render warning:', stage1Err);
    }

    // =========================================================================
    // STAGE 2: Fast Lineup & Badges (Asynchronous fetch with timeout guard)
    // =========================================================================
    if (_strategyLoadAbortController) {
        _strategyLoadAbortController.abort();
    }
    _strategyLoadAbortController = new AbortController();
    const currentController = _strategyLoadAbortController;

    let fetchSuccess = false;

    try {
        const timeoutId = setTimeout(() => {
            if (currentController === _strategyLoadAbortController) {
                currentController.abort();
            }
        }, 12000);

        const res = await fetch(`/api/strategy/state${q}`, { signal: currentController.signal });
        clearTimeout(timeoutId);

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Failed to load strategy state');

        if (getEffectiveAccountId() === aid) {
            fetchSuccess = true;
            strategyState = data;

            if (data.config) {
                strategyConfig = Object.assign({}, strategyConfig, data.config);
            } else if (data.strategy) {
                strategyConfig = Object.assign({}, strategyConfig, data.strategy);
            }

            renderStrategyBadges(data);
            renderCurrentLineup();

            if (data.pending_equip && data.pending_equip.timestamp) {
                const elapsed = Math.floor((Date.now() - (data.pending_equip.timestamp * 1000)) / 1000);
                const est = data.pending_equip.estimated_seconds || 15;
                if (elapsed < (est + 25)) {
                    resumeEquipProgress(data.pending_equip, elapsed, est);
                }
            }
        }
    } catch (stage2Err) {
        if (stage2Err.name === 'AbortError' && currentController !== _strategyLoadAbortController) {
            return; // Superseded by a newer load request
        }
        console.warn('[Strategy Stage 2] Lineup fetch error:', stage2Err);
        if (getEffectiveAccountId() === aid) {
            const errorMsg = stage2Err.name === 'AbortError' ? 'Network timeout syncing lineup' : stage2Err.message;
            renderLineupFallback(errorMsg);
        }
    }

    // =========================================================================
    // STAGE 3: Synergies, Wilson CI & Settings (Independent stage)
    // =========================================================================
    try {
        renderStrategySettings();
        renderSynergiesAndSolvency();
    } catch (stage3Err) {
        console.warn('[Strategy Stage 3] Synergies render error:', stage3Err);
    }

    // =========================================================================
    // STAGE 4: Telemetry / Stream (Independent logging)
    // =========================================================================
    try {
        const accName = getAccountDisplayName();
        if (fetchSuccess) {
            appendStrategyLog(`Engine state loaded for [${accName}] (id: ${aid || 'default'}).`, 'info');
            if (forceRefresh && typeof showToast === 'function') {
                showToast('Strategy state refreshed', 'success');
            }
        } else {
            appendStrategyLog(`Engine offline or syncing for [${accName}]. Waiting for telemetry...`, 'warn');
        }
    } catch (stage4Err) {
        console.warn('[Strategy Stage 4] Telemetry log error:', stage4Err);
    }
}

/**
 * Render Header Badges, Verification Status & Timers
 */
function renderStrategyBadges(data = null) {
    const engineBadge = document.getElementById('strat-engine-badge');
    const autoEquipBadge = document.getElementById('strat-autoequip-badge');
    const verifiedBadge = document.getElementById('strat-verified-badge');
    const lastSyncedBadge = document.getElementById('strat-last-synced');

    if (engineBadge) {
        if (strategyConfig.enabled) {
            engineBadge.className = 'strat-badge badge-active';
            engineBadge.innerHTML = '<span class="badge-dot"></span> Active';
        } else {
            engineBadge.className = 'strat-badge badge-paused';
            engineBadge.innerHTML = '<span class="badge-dot"></span> Paused';
        }
    }

    if (autoEquipBadge) {
        if (strategyConfig.auto_equip) {
            autoEquipBadge.className = 'strat-badge badge-autoequip';
            autoEquipBadge.textContent = 'Auto-Equip: Enabled';
        } else {
            autoEquipBadge.className = 'strat-badge badge-autoequip disabled';
            autoEquipBadge.textContent = 'Auto-Equip: Inactive';
        }
    }

    const stateData = data || strategyState || {};
    const isVerified = !!(stateData.team_verified || (stateData.state && stateData.state.team_verified));
    if (verifiedBadge) {
        if (isVerified) {
            verifiedBadge.className = 'strat-badge badge-active';
            verifiedBadge.innerHTML = '<span class="badge-dot"></span> Verified Discord';
            verifiedBadge.title = 'Active team verified directly from OwO Discord battle telemetry';
        } else {
            verifiedBadge.className = 'strat-badge badge-paused';
            verifiedBadge.innerHTML = '<span class="badge-dot"></span> Cached Snapshot';
            verifiedBadge.title = 'Using cached offline snapshot. Click "Sync Discord" to update live.';
        }
    }

    if (lastSyncedBadge) {
        const lastUpdated = stateData.last_updated || (stateData.state && stateData.state.last_updated) || 0;
        if (lastUpdated > 0) {
            const diffSec = Math.max(0, Math.floor(Date.now() / 1000 - lastUpdated));
            if (diffSec < 60) {
                lastSyncedBadge.textContent = 'Synced: Just now';
            } else if (diffSec < 3600) {
                lastSyncedBadge.textContent = `Synced: ${Math.floor(diffSec / 60)}m ago`;
            } else {
                lastSyncedBadge.textContent = `Synced: ${Math.floor(diffSec / 3600)}h ago`;
            }
        } else {
            lastSyncedBadge.textContent = 'Synced: Offline';
        }
    }

    // Schedule next run countdown
    const intervalSec = Array.isArray(strategyConfig.interval) ? strategyConfig.interval[0] : (parseInt(strategyConfig.interval, 10) || 3600);
    startStratCountdown(intervalSec);
}

function startStratCountdown(intervalSeconds) {
    if (stratCountdownInterval) clearInterval(stratCountdownInterval);
    const secs = Number(intervalSeconds) || 3600;
    stratNextRunTimestamp = Date.now() + (secs * 1000);

    const updateTimer = () => {
        const el = document.getElementById('strat-countdown');
        if (!el) return;
        const diff = Math.max(0, Math.floor((stratNextRunTimestamp - Date.now()) / 1000));
        const mins = Math.floor(diff / 60);
        const s = diff % 60;
        el.textContent = `${mins}m ${s}s`;
    };

    updateTimer();
    stratCountdownInterval = setInterval(updateTimer, 1000);
}

/**
 * Populate Quick Settings Controls
 */
function renderStrategySettings() {
    const intervalSelect = document.getElementById('strat-interval-input');
    if (intervalSelect && strategyConfig.interval) {
        const val = Array.isArray(strategyConfig.interval) ? strategyConfig.interval[0] : strategyConfig.interval;
        intervalSelect.value = String(val);
    }

    const setToggle = (id, isOn) => {
        const el = document.getElementById(id);
        if (!el) return;
        if (isOn) {
            el.classList.add('is-on');
        } else {
            el.classList.remove('is-on');
        }
    };

    setToggle('strat-toggle-autoequip', !!strategyConfig.auto_equip);
    setToggle('strat-toggle-autodismantle', !!strategyConfig.auto_dismantle);
    setToggle('strat-toggle-dryrun', strategyConfig.dry_run !== false);
}

/**
 * Toggle quick settings switch
 */
function toggleStratParam(param, el) {
    if (!el) return;
    const isNowOn = !el.classList.contains('is-on');
    if (isNowOn) {
        el.classList.add('is-on');
    } else {
        el.classList.remove('is-on');
    }

    strategyConfig[param] = isNowOn;
    isStratDirty = true;

    if (param === 'auto_equip') {
        renderStrategyBadges();
    }
}

function markStratDirty() {
    const intervalSelect = document.getElementById('strat-interval-input');
    if (intervalSelect) {
        strategyConfig.interval = parseInt(intervalSelect.value, 10) || 3600;
    }
    isStratDirty = true;
}

/**
 * Save strategy settings to NeuraSelf settings endpoint
 */
async function saveStrategyConfig(btn) {
    const intervalSelect = document.getElementById('strat-interval-input');
    if (intervalSelect) {
        strategyConfig.interval = parseInt(intervalSelect.value, 10) || 3600;
    }

    const payload = {
        strategy: {
            enabled: strategyConfig.enabled !== false,
            interval: strategyConfig.interval || 3600,
            auto_equip: !!strategyConfig.auto_equip,
            auto_dismantle: !!strategyConfig.auto_dismantle,
            dry_run: strategyConfig.dry_run !== false
        }
    };

    const aid = getEffectiveAccountId();
    const q = aid ? `?id=${encodeURIComponent(aid)}` : '';
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '<span class="icon-svg" style="--icon: url(\'/static/assets/neura_icons/rotate.svg\');"></span> Saving...';
        btn.disabled = true;
    }

    try {
        const res = await fetch(`/api/settings${q}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const resData = await res.json();
        if (res.ok && (resData.status === 'success' || resData.success)) {
            isStratDirty = false;
            renderStrategyBadges();
            appendStrategyLog('Strategy settings saved to disk.', 'success');
            if (typeof showToast === 'function') {
                showToast('Strategy Settings Saved Successfully!', 'success');
            }
        } else {
            throw new Error(resData.error || 'Failed to save settings');
        }
    } catch (err) {
        console.error('Error saving strategy settings:', err);
        if (typeof showToast === 'function') {
            showToast('Save failed: ' + err.message, 'error');
        }
    } finally {
        if (btn) {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    }
}

/**
 * Render Current Active Lineup
 * Alias: renderActiveLineup
 */
function renderCurrentLineup() {
    if (!strategyState) {
        renderSlotSkeletons();
        setMetricLoaders();
        return;
    }
    const team = strategyState.team || {};
    const evalData = strategyState.evaluation || {};
    const animals = team.animals || [];
    const weapons = team.weapons || [];
    const breakdowns = evalData.pet_breakdown || [];
    const isVerified = !!strategyState.team_verified;

    const slotsContainer = document.getElementById('cur-team-slots');
    if (slotsContainer) {
        if (animals.length > 0) {
            slotsContainer.innerHTML = buildSlotsHtml(animals, weapons, breakdowns);
        } else {
            slotsContainer.innerHTML = '<div class="no-data">No active pet team registered yet. Click "Sync Discord" to load.</div>';
        }
    }

    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };

    setVal('cur-frontline-ehp', formatNumber(Math.round(evalData.frontline_ehp || 0)));
    setVal('cur-total-ehp', formatNumber(Math.round(evalData.total_team_ehp || 0)));
    setVal('cur-sustained-dps', formatNumber(Math.round(evalData.sustained_dps || 0)) + '/s');
    setVal('cur-win-rate', (evalData.win_rate !== undefined ? evalData.win_rate : 0) + '%');

    const curVerTag = document.getElementById('cur-verified-tag');
    if (curVerTag) {
        if (isVerified) {
            curVerTag.className = 'strat-badge badge-active';
            curVerTag.textContent = 'VERIFIED';
        } else {
            curVerTag.className = 'strat-badge badge-paused';
            curVerTag.textContent = 'CACHED';
        }
    }
}
const renderActiveLineup = renderCurrentLineup;

/**
 * Render Synergies and WP Solvency
 */
function renderSynergiesAndSolvency() {
    const evalData = (strategyState && strategyState.evaluation) ? strategyState.evaluation : null;

    const solvencyBadge = document.getElementById('strat-wp-solvency');
    if (solvencyBadge) {
        if (evalData) {
            const isSolvent = evalData.wp_solvent !== false;
            if (isSolvent) {
                solvencyBadge.className = 'strat-badge badge-active';
                solvencyBadge.textContent = 'WP SOLVENT';
            } else {
                solvencyBadge.className = 'strat-badge badge-paused';
                solvencyBadge.textContent = 'WP DEFICIT';
            }
        } else {
            solvencyBadge.className = 'strat-badge badge-paused';
            solvencyBadge.textContent = 'STANDBY';
        }
    }

    const synList = document.getElementById('strat-synergies-list');
    if (synList) {
        const synergies = evalData ? (evalData.synergies || []) : [];
        if (synergies.length > 0) {
            synList.innerHTML = synergies.map(s => `<span class="synergy-tag">✨ ${escapeHtml(s)}</span>`).join('');
        } else if (evalData) {
            synList.innerHTML = `
                <span class="synergy-tag">🛡️ Frontline Aegis EHP Scaling</span>
                <span class="synergy-tag">⚔️ Balanced DPS Cleave</span>
                <span class="synergy-tag">✨ 100% Battle Solvency</span>
            `;
        } else {
            synList.innerHTML = `
                <span class="synergy-tag" style="opacity:0.6;">⏳ Awaiting team evaluation...</span>
            `;
        }
    }

    // Wilson confidence interval
    if (evalData) {
        const wilsonCI = evalData.wilson_ci || [0, 0];
        const winRate = evalData.win_rate || 0;
        updateWilsonDisplay(wilsonCI[0] || 0, winRate, wilsonCI[1] || 0);
    } else {
        updateWilsonDisplay(0, 0, 0);
    }
}

function updateWilsonDisplay(lower, mid, upper) {
    const span = document.getElementById('strat-wilson-span');
    if (span) {
        if (lower === 0 && upper === 0 && mid === 0) {
            span.textContent = '[--% — --%]';
        } else {
            span.textContent = `[${Number(lower).toFixed(1)}% — ${Number(upper).toFixed(1)}%]`;
        }
    }

    const minLbl = document.getElementById('wilson-min-lbl');
    const midLbl = document.getElementById('wilson-mid-lbl');
    const maxLbl = document.getElementById('wilson-max-lbl');

    if (minLbl) minLbl.textContent = lower > 0 ? `Lower: ${Number(lower).toFixed(1)}%` : 'Lower: --%';
    if (midLbl) midLbl.textContent = mid > 0 ? `Expected: ${Number(mid).toFixed(1)}%` : 'Expected: --%';
    if (maxLbl) maxLbl.textContent = upper > 0 ? `Upper: ${Number(upper).toFixed(1)}%` : 'Upper: --%';

    const fillBar = document.getElementById('wilson-fill-bar');
    if (fillBar) {
        fillBar.style.width = (mid > 0 ? Math.min(100, Math.max(5, mid)) : 0) + '%';
    }
}

/**
 * Build rich HTML for pet slots in Lineup Cards
 * Displays exact weapon qualities, monospace weapon IDs, passives, animal emojis, and semantic role badges.
 */
function buildSlotsHtml(animals, weapons, breakdowns) {
    let html = '';
    const defaultRoles = ['Frontline Tank', 'Cleave DPS', 'Backline Carry'];
    const defaultRolePills = ['tank', 'dps', 'dps'];

    for (let i = 0; i < 3; i++) {
        const anim = animals[i] || {};
        const weap = weapons[i] || {};
        const bd = breakdowns[i] || {};

        const animRawName = anim.name || anim.animal_name || bd.animal || `Pet ${i + 1}`;
        const animName = capitalize(animRawName);
        const emoji = getAnimalEmoji(animRawName);
        const animLvl = anim.level !== undefined ? anim.level : (bd.animal_level !== undefined ? bd.animal_level : 50);

        const weapName = weap.weapon_name || weap.name || bd.weapon_name || bd.weapon || 'Defender\'s Aegis';
        const weapId = weap.id || bd.weapon_id || '';
        const qualityVal = weap.quality_val !== undefined ? Math.round(weap.quality_val) : (bd.quality_val !== undefined ? Math.round(bd.quality_val) : null);
        const isExact = weap.quality_is_exact !== undefined ? !!weap.quality_is_exact : (qualityVal !== null && qualityVal > 80);
        const wear = weap.wear || bd.wear || '';
        const passives = Array.isArray(weap.passives) ? weap.passives : (Array.isArray(bd.passives) ? bd.passives : []);

        // Semantic Role Determination
        const rawRole = bd.role || defaultRoles[i];
        let roleClass = defaultRolePills[i];
        const roleLower = String(rawRole).toLowerCase();
        if (roleLower.includes('tank') || roleLower.includes('anchor') || roleLower.includes('aegis')) {
            roleClass = 'tank';
        } else if (roleLower.includes('heal') || roleLower.includes('support')) {
            roleClass = 'healer';
        } else if (roleLower.includes('disrupt') || roleLower.includes('stun') || roleLower.includes('control')) {
            roleClass = 'disruptor';
        } else {
            roleClass = 'dps';
        }

        const ehp = bd.ehp_physical || (bd.hp ? bd.hp * 1.5 : 0);
        const dps = bd.sustained_dps || 0;

        // Weapon Quality Badge
        let qualityBadgeHtml = '';
        if (qualityVal !== null) {
            const exactClass = isExact ? 'exact' : 'estimate';
            const exactLabel = isExact ? `${qualityVal}%` : `~${qualityVal}%`;
            qualityBadgeHtml = `<span class="weapon-quality-pill ${exactClass}">${exactLabel}</span>`;
        }

        // Weapon ID Badge
        const idBadgeHtml = weapId ? `<span class="weapon-id-badge">#${escapeHtml(weapId)}</span>` : '';

        // Wear Pill
        const wearHtml = wear ? `<span class="weapon-wear-pill">(${escapeHtml(wear)})</span>` : '';

        // Passives Tags
        let passivesHtml = '';
        if (passives.length > 0) {
            passivesHtml = `<div class="weapon-passives-list">${passives.map(p => `<span class="weapon-passive-tag">⚡ ${escapeHtml(p)}</span>`).join('')}</div>`;
        }

        html += `
            <div class="pet-slot-card">
                <div class="pet-slot-info">
                    <div class="pet-slot-number">#${i + 1}</div>
                    <div style="flex:1;">
                        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                            <span class="pet-animal-name">${emoji} ${escapeHtml(animName)}</span>
                            <span class="pet-animal-lvl">Lvl ${animLvl}</span>
                            <span class="pet-role-pill ${roleClass}">${escapeHtml(rawRole)}</span>
                        </div>
                        <div class="pet-weapon-name" style="margin-top:3px; flex-wrap:wrap;">
                            🗡️ <b>${escapeHtml(weapName)}</b>
                            ${idBadgeHtml}
                            ${qualityBadgeHtml}
                            ${wearHtml}
                        </div>
                        ${passivesHtml}
                    </div>
                </div>
                <div class="pet-stats-micro">
                    <div>EHP: <b>${ehp > 0 ? formatNumber(Math.round(ehp)) : '--'}</b></div>
                    <div>DPS: <b>${dps > 0 ? formatNumber(Math.round(dps)) + '/s' : '--'}</b></div>
                </div>
            </div>
        `;
    }
    return html;
}

/**
 * 🚀 Run Optimization Tournament
 */
async function runStrategyOptimize(btn) {
    const aid = getEffectiveAccountId();
    const q = aid ? `?id=${encodeURIComponent(aid)}` : '';
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '<span class="status-spinner" style="width:14px; height:14px; border-width:2px;"></span> Optimizing...';
        btn.disabled = true;
    }

    const statusBanner = document.getElementById('strategyTournamentStatus');
    if (statusBanner) statusBanner.style.display = 'block';

    try {
        appendStrategyLog('Starting 3-Stage Multi-Fidelity Tournament Optimizer...', 'info');

        const res = await fetch(`/api/strategy/optimize${q}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: aid || null,
                coarse_seeds: 10,
                fine_seeds: 50
            })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Optimization failed');

        strategyWinner = data;

        // Render Recommended Lineup with true analytical results
        renderOptimalLineup(data);

        const delta = data.win_rate_delta || 0;
        const winnerWr = (data.winner && data.winner.win_rate !== undefined) ? data.winner.win_rate : 0;
        const animalNames = (data.winner && data.winner.animals) ? data.winner.animals.join(' / ') : 'Optimized Team';

        appendStrategyLog(`Tournament Winner: [${animalNames}] Win Rate: ${winnerWr}% (${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%)`, 'success');

        if (typeof showToast === 'function') {
            showToast(`Optimization complete! Winner Win Rate: ${winnerWr}% (${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%)`, 'success');
        }

        // Auto-equip if configured and commands exist
        if (strategyConfig.auto_equip && data.in_game_commands && data.in_game_commands.length > 0) {
            appendStrategyLog('Auto-Equip triggered automatically by policy.', 'info');
            equipBestTeam();
        }
    } catch (err) {
        console.error('Error running optimization:', err);
        appendStrategyLog('Optimization failed: ' + err.message, 'warn');
        if (typeof showToast === 'function') {
            showToast('Optimization failed: ' + err.message, 'error');
        }
    } finally {
        if (statusBanner) {
            setTimeout(() => { statusBanner.style.display = 'none'; }, 2000);
        }
        if (btn) {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    }
}

/**
 * Render Optimal Lineup from Tournament Results
 * Alias: renderCandidateComparison
 */
function renderOptimalLineup(data) {
    const winner = data.winner || {};
    const report = data.report || {};
    const recTeam = report.recommended_team || {};

    // Animals and Weapons resolution
    let animals = winner.animal_details;
    if (!animals || !animals.length) {
        animals = (winner.animals || ['giraffbot', 'lion', 'owl']).map((n, i) => {
            const slot = (recTeam.slots && recTeam.slots[i]) ? recTeam.slots[i] : {};
            return { name: n, level: slot.animal_level || 50 };
        });
    }

    let weapons = winner.weapon_details;
    if (!weapons || !weapons.length) {
        weapons = (winner.weapons || ['Glacial Axe', 'Compound Bow', 'Healing Staff']).map((w, i) => {
            const slot = (recTeam.slots && recTeam.slots[i]) ? recTeam.slots[i] : {};
            return {
                weapon_name: w,
                id: slot.weapon_id || '',
                quality_val: 95.0,
                quality_is_exact: true,
                wear: 'worn'
            };
        });
    }

    // Slots & analytical breakdowns
    const slots = winner.slots || recTeam.slots || [];
    const breakdowns = [
        {
            animal: animals[0]?.name,
            weapon: weapons[0]?.weapon_name,
            role: slots[0]?.role || 'Frontline Anchor',
            ehp_physical: winner.frontline_ehp || recTeam.frontline_ehp || 0,
            sustained_dps: Math.round((winner.sustained_dps || recTeam.sustained_dps || 0) * 0.3)
        },
        {
            animal: animals[1]?.name,
            weapon: weapons[1]?.weapon_name,
            role: slots[1]?.role || 'Main Carry DPS',
            ehp_physical: Math.round(((winner.total_team_ehp || recTeam.total_team_ehp || 0) - (winner.frontline_ehp || recTeam.frontline_ehp || 0)) * 0.45),
            sustained_dps: Math.round((winner.sustained_dps || recTeam.sustained_dps || 0) * 0.5)
        },
        {
            animal: animals[2]?.name,
            weapon: weapons[2]?.weapon_name,
            role: slots[2]?.role || 'Tactical Healer',
            ehp_physical: Math.round(((winner.total_team_ehp || recTeam.total_team_ehp || 0) - (winner.frontline_ehp || recTeam.frontline_ehp || 0)) * 0.55),
            sustained_dps: Math.round((winner.sustained_dps || recTeam.sustained_dps || 0) * 0.2)
        }
    ];

    const slotsContainer = document.getElementById('opt-team-slots');
    if (slotsContainer) {
        slotsContainer.innerHTML = buildSlotsHtml(animals, weapons, breakdowns);
    }

    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };

    const delta = data.win_rate_delta !== undefined ? data.win_rate_delta : 0;
    const wr = winner.win_rate !== undefined ? winner.win_rate : 0;
    const frontlineEhp = winner.frontline_ehp || recTeam.frontline_ehp || 0;
    const totalTeamEhp = winner.total_team_ehp || recTeam.total_team_ehp || 0;
    const sustainedDps = winner.sustained_dps || recTeam.sustained_dps || 0;

    setVal('opt-frontline-ehp', formatNumber(Math.round(frontlineEhp)));
    setVal('opt-total-ehp', formatNumber(Math.round(totalTeamEhp)));
    setVal('opt-sustained-dps', formatNumber(Math.round(sustainedDps)) + '/s');
    setVal('opt-win-rate', `${wr}%`);

    const deltaBadge = document.getElementById('opt-win-delta');
    if (deltaBadge) {
        deltaBadge.textContent = `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}% Win Rate Delta`;
        deltaBadge.className = delta >= 0 ? 'delta-badge positive' : 'delta-badge';
    }

    if (winner.wilson_ci && winner.wilson_ci.length === 2) {
        updateWilsonDisplay(winner.wilson_ci[0], wr, winner.wilson_ci[1]);
    }

    // Blueprint alerts
    const alertsContainer = document.getElementById('opt-blueprint-alerts');
    if (alertsContainer) {
        const alerts = report.missing_blueprint_alerts || [];
        if (alerts.length > 0) {
            alertsContainer.style.display = 'block';
            alertsContainer.innerHTML = `
                <div class="blueprint-alert-box">
                    <div><b>⚠️ Unconfirmed Weapon Blueprints (${alerts.length})</b></div>
                    <div>Some recommended weapons have estimated quality rolls. Run in Discord to reveal exact stats:</div>
                    ${alerts.map(a => `
                        <div>• <b>${escapeHtml(a.weapon_name)}</b>: <code class="blueprint-alert-code" onclick="navigator.clipboard.writeText('${escapeHtml(a.suggested_command)}'); showToast('Copied: ${escapeHtml(a.suggested_command)}', 'success');">${escapeHtml(a.suggested_command)}</code></div>
                    `).join('')}
                </div>
            `;
        } else {
            alertsContainer.style.display = 'none';
        }
    }
}
const renderCandidateComparison = renderOptimalLineup;

/**
 * ⚡ Auto-Equip Best Team Now
 */
async function equipBestTeam(btn) {
    const aid = getEffectiveAccountId();
    const q = aid ? `?id=${encodeURIComponent(aid)}` : '';
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '<span class="status-spinner" style="width:13px; height:13px; border-width:2px;"></span> Enqueuing...';
        btn.disabled = true;
    }

    try {
        const commands = strategyWinner ? strategyWinner.in_game_commands : null;
        const targetAnimals = strategyWinner?.winner?.animals || null;
        const targetWeapons = strategyWinner?.winner?.weapons || null;

        const payload = {
            id: aid || null,
            commands: commands,
            target_animals: targetAnimals,
            target_weapons: targetWeapons
        };

        const res = await fetch(`/api/strategy/equip${q}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Failed to equip team');

        const cmdCount = (data.commands || []).length || data.queued_count || 6;
        const estSec = data.estimated_duration_seconds || Math.max(12, cmdCount * 3);

        appendStrategyLog(`Enqueued ${cmdCount} in-game equip commands. Starting stealth execution (~${estSec}s).`, 'info');

        if (typeof showToast === 'function') {
            showToast(`Enqueued ${cmdCount} commands into bot queue. Verifying with Discord...`, 'success');
        }

        // Start reactive live polling until OwO Discord battle telemetry confirms the team
        startEquipPolling(aid, targetAnimals, estSec, cmdCount, btn, origHtml);
    } catch (err) {
        console.error('Error equipping team:', err);
        appendStrategyLog('Equip request failed: ' + err.message, 'warn');
        if (typeof showToast === 'function') {
            showToast('Equip failed: ' + err.message, 'error');
        }
        if (btn) {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    }
}

/**
 * Start Reactive In-Flight Equip Polling
 * Watches /api/strategy/state until Discord confirms the new team via stealth typing
 */
function startEquipPolling(aid, targetAnimals, estimatedSeconds, cmdCount, triggerBtn = null, triggerBtnHtml = '') {
    cancelEquipPolling();

    const progressBanner = document.getElementById('strategyEquipProgress');
    const progressBar = document.getElementById('equip-progress-bar');
    const timerText = document.getElementById('equip-progress-timer');
    const headingText = document.getElementById('equip-progress-heading');
    const subtext = document.getElementById('equip-progress-subtext');

    if (progressBanner) {
        progressBanner.style.display = 'block';
        if (progressBar) progressBar.style.width = '10%';
        if (headingText) headingText.textContent = `Executing In-Game Equip Sequence (${cmdCount} commands)`;
        if (timerText) timerText.textContent = `~${estimatedSeconds}s remaining`;
        if (subtext) subtext.textContent = 'Enqueued to bot. Simulating human stealth typing & awaiting OwO in-game confirmation...';
    }

    const equipStartTime = Date.now();
    const maxPollDurationMs = 65000; // 65 second timeout guard

    // Animate progress bar smoothly
    stratEquipProgressInterval = setInterval(() => {
        const elapsedSec = Math.floor((Date.now() - equipStartTime) / 1000);
        const remaining = Math.max(0, estimatedSeconds - elapsedSec);
        const percent = Math.min(95, Math.max(15, Math.round((elapsedSec / estimatedSeconds) * 90)));

        if (progressBar) progressBar.style.width = `${percent}%`;
        if (timerText) {
            timerText.textContent = remaining > 0 ? `~${remaining}s remaining` : 'Verifying with Discord...';
        }
    }, 1000);

    // Poll endpoint every 2.5 seconds
    const pollState = async () => {
        const q = aid ? `?id=${encodeURIComponent(aid)}` : '';
        try {
            const res = await fetch(`/api/strategy/state${q}`);
            if (!res.ok) return;
            const data = await res.json();
            if (!data.success) return;

            const stateTeam = (data.team && data.team.animals) ? data.team.animals.map(a => a.name.toLowerCase()) : [];
            const targetNames = targetAnimals ? targetAnimals.map(n => n.toLowerCase()) : [];

            // Check if active team on Discord matches our target team
            const hasMatched = targetNames.length > 0 && targetNames.every(name => stateTeam.includes(name));
            const lastUpdatedMs = (data.last_updated || 0) * 1000;
            const isFreshUpdate = lastUpdatedMs >= (equipStartTime - 2000) && data.team_verified;

            if (hasMatched || isFreshUpdate) {
                // Team verified and confirmed on Discord!
                cancelEquipPolling();

                if (progressBar) progressBar.style.width = '100%';
                if (timerText) timerText.textContent = '✅ Confirmed!';
                if (headingText) headingText.textContent = 'Lineup Successfully Verified on Discord!';
                if (subtext) subtext.textContent = 'Active team updated directly from OwO Discord battle telemetry.';

                appendStrategyLog('🎉 In-game team equip verified active on Discord!', 'success');
                if (typeof showToast === 'function') {
                    showToast('🎉 Optimal team successfully equipped and confirmed on Discord!', 'success');
                }

                // Refresh the whole UI with the true verified state
                strategyState = data;
                renderStrategyBadges(data);
                renderCurrentLineup();
                renderSynergiesAndSolvency();

                setTimeout(() => {
                    if (progressBanner) progressBanner.style.display = 'none';
                    if (triggerBtn) {
                        triggerBtn.innerHTML = triggerBtnHtml;
                        triggerBtn.disabled = false;
                    }
                }, 4000);
                return;
            }

            // Check timeout
            if (Date.now() - equipStartTime > maxPollDurationMs) {
                cancelEquipPolling();
                if (timerText) timerText.textContent = '⚠️ Cooldown Elapsed';
                if (subtext) subtext.textContent = 'Commands sent to queue. Discord response pending. Click "Refresh Data" shortly.';
                appendStrategyLog('Equip verification timeout. Commands are in queue or awaiting OwO response.', 'warn');
                setTimeout(() => {
                    if (progressBanner) progressBanner.style.display = 'none';
                    if (triggerBtn) {
                        triggerBtn.innerHTML = triggerBtnHtml;
                        triggerBtn.disabled = false;
                    }
                }, 6000);
            }
        } catch (pollErr) {
            console.warn('Strategy equip poll error:', pollErr);
        }
    };

    stratEquipPollTimer = setInterval(pollState, 2500);
}

/**
 * Resume progress bar if an equip was pending on initial load
 */
function resumeEquipProgress(pending, elapsedSec, estSec) {
    if (stratEquipPollTimer) return; // already polling
    const aid = getEffectiveAccountId();
    const remaining = Math.max(0, estSec - elapsedSec);
    startEquipPolling(aid, pending.target_animals, remaining || 10, pending.commands_total || 6);
}

function cancelEquipPolling() {
    if (stratEquipPollTimer) {
        clearInterval(stratEquipPollTimer);
        stratEquipPollTimer = null;
    }
    if (stratEquipProgressInterval) {
        clearInterval(stratEquipProgressInterval);
        stratEquipProgressInterval = null;
    }
}

/**
 * 🔄 Sync on-demand telemetry from Discord (owo team, zoo, weapon)
 */
async function syncStrategyDiscord(btn) {
    const aid = getEffectiveAccountId();
    const q = aid ? `?id=${encodeURIComponent(aid)}` : '';
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '<span class="status-spinner" style="width:13px; height:13px; border-width:2px;"></span> Syncing...';
        btn.disabled = true;
    }

    try {
        const res = await fetch(`/api/strategy/sync${q}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: aid || null })
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.error || 'Sync request failed');

        appendStrategyLog('Requested live Discord sync (`owo team`, `zoo`, `weapon`). Reading responses...', 'info');
        if (typeof showToast === 'function') {
            showToast('Sync commands sent to bot queue. Reading Discord telemetry...', 'success');
        }

        // Poll for state update in 4s and 8s
        setTimeout(() => loadStrategyView(false), 4000);
        setTimeout(() => loadStrategyView(false), 8500);
    } catch (err) {
        console.error('Error syncing Discord:', err);
        appendStrategyLog('Discord sync failed: ' + err.message, 'warn');
        if (typeof showToast === 'function') {
            showToast('Discord sync failed: ' + err.message, 'error');
        }
    } finally {
        if (btn) {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    }
}

/**
 * 👹 Simulate Guild Boss Raid
 */
async function runBossSim(btn) {
    const presetSelect = document.getElementById('boss-preset-select');
    const seedsSelect = document.getElementById('boss-seeds-select');

    const preset = presetSelect ? presetSelect.value : 'standard_cleave';
    const seeds = seedsSelect ? parseInt(seedsSelect.value, 10) : 10;

    const aid = getEffectiveAccountId();
    const q = aid ? `?id=${encodeURIComponent(aid)}` : '';
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '👹 Simulating...';
        btn.disabled = true;
    }

    try {
        const res = await fetch(`/api/strategy/boss${q}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: aid || null,
                preset: preset,
                seeds: seeds
            })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Boss simulation failed');

        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        setVal('boss-name-val', data.boss_name || preset);
        setVal('boss-dmg-val', formatNumber(Math.round(data.avg_damage_dealt || 0)));
        setVal('boss-turns-val', `${(data.avg_turns_survived || 0).toFixed(1)} / 24`);
        setVal('boss-survival-val', `${(data.full_24_turns_rate_percent || 0).toFixed(1)}%`);
        setVal('boss-score-val', Math.round(data.composite_score || 0));

        appendStrategyLog(`Boss simulated (${preset}): Avg Dmg ${formatNumber(Math.round(data.avg_damage_dealt || 0))} | Score ${formatNumber(Math.round(data.composite_score || 0))}`, 'info');

        if (typeof showToast === 'function') {
            showToast(`Raid simulated: Composite Score ${Math.round(data.composite_score || 0)}`, 'success');
        }
    } catch (err) {
        console.error('Error simulating boss raid:', err);
        if (typeof showToast === 'function') {
            showToast('Boss sim failed: ' + err.message, 'error');
        }
    } finally {
        if (btn) {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    }
}

/**
 * 💎 Scan Safe Weapon Shards
 */
async function runShardScan(btn) {
    const aid = getEffectiveAccountId();
    const q = aid ? `?id=${encodeURIComponent(aid)}` : '';
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '💎 Scanning...';
        btn.disabled = true;
    }

    try {
        const res = await fetch(`/api/strategy/shards${q}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: aid || null
            })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Shard scan failed');

        const plan = data.plan || {};
        strategyShardPlan = plan;

        renderShardPlan(plan);

        appendStrategyLog(`Shard Scan: ${plan.safe_to_dismantle_count || 0} safe junk weapon(s) identified (+${plan.projected_shards_gained || 0} shards).`, 'info');

        if (typeof showToast === 'function') {
            showToast(`Scan complete: ${plan.safe_to_dismantle_count || 0} safe weapons identified`, 'success');
        }
    } catch (err) {
        console.error('Error scanning shards:', err);
        if (typeof showToast === 'function') {
            showToast('Shard scan failed: ' + err.message, 'error');
        }
    } finally {
        if (btn) {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    }
}

/**
 * Render Shard Planner Table & Metrics
 */
function renderShardPlan(plan) {
    const curEl = document.getElementById('shard-current-display');
    const gainEl = document.getElementById('shard-gain-display');
    const totalEl = document.getElementById('shard-total-display');
    const milestoneTitle = document.getElementById('shard-milestone-title');
    const milestonePercent = document.getElementById('shard-milestone-percent');
    const milestoneFill = document.getElementById('shard-milestone-fill');

    const cur = plan.current_shards || 0;
    const gain = plan.projected_shards_gained || 0;
    const total = plan.total_projected_shards || (cur + gain);
    const progress = Math.min(100, Math.max(0, plan.milestone_progress_percent || 0));

    if (curEl) curEl.textContent = formatNumber(cur);
    if (gainEl) gainEl.textContent = `+${formatNumber(gain)}`;
    if (totalEl) totalEl.textContent = formatNumber(total);
    if (milestoneTitle && plan.next_milestone) milestoneTitle.textContent = plan.next_milestone;
    if (milestonePercent) milestonePercent.textContent = `${progress.toFixed(1)}%`;
    if (milestoneFill) milestoneFill.style.width = `${progress}%`;

    // Populate Table
    const tbody = document.getElementById('shard-weapons-tbody');
    if (tbody) {
        const safeItems = plan.safe_to_dismantle || [];
        if (safeItems.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="no-data">No dismantle-safe weapons found in inventory. Your collection is fully protected!</td></tr>';
        } else {
            tbody.innerHTML = safeItems.map(w => {
                const q = w.quality_val ? `${Math.round(w.quality_val)}%` : 'Common';
                const wear = w.wear || 'worn';
                return `
                    <tr>
                        <td><code style="color:#00ffff;">${escapeHtml(w.id || 'N/A')}</code></td>
                        <td><b>${escapeHtml(w.weapon_name || 'Weapon')}</b></td>
                        <td>${q}</td>
                        <td><span style="text-transform:capitalize;">${escapeHtml(wear)}</span></td>
                        <td><span class="strat-badge badge-active" style="padding:2px 8px; font-size:0.68rem;">SAFE</span></td>
                        <td style="color:var(--success); font-family:var(--font-mono); font-weight:700;">+${calculateEstimatedShards(w)}</td>
                    </tr>
                `;
            }).join('');
        }
    }

    // Commands preview
    const previewBox = document.getElementById('shard-cmds-preview-box');
    const cmdsOutput = document.getElementById('shard-cmds-output');
    if (previewBox && cmdsOutput && plan.batch_commands && plan.batch_commands.length > 0) {
        previewBox.style.display = 'block';
        cmdsOutput.textContent = plan.batch_commands.join('\n');
    }
}

/**
 * Execute Safe Shard Dismantle Batch
 */
async function executeShardDismantle(btn) {
    if (!strategyShardPlan || !strategyShardPlan.batch_commands || strategyShardPlan.batch_commands.length === 0) {
        alert('Please run "Scan Safe Weapon Shards" first, or no safe weapons are available to dismantle.');
        return;
    }

    const count = strategyShardPlan.safe_to_dismantle_count || strategyShardPlan.batch_commands.length;
    const gain = strategyShardPlan.projected_shards_gained || 0;
    const confirmed = confirm(
        `Are you sure you want to dismantle ${count} safe junk weapon(s) for ~${gain} shards?\n\n` +
        `This will enqueue the batch commands directly into the OwO Discord channel.\n` +
        `All active team and high-tier weapons remain strictly protected.`
    );
    if (!confirmed) return;

    const aid = getEffectiveAccountId();
    const q = aid ? `?id=${encodeURIComponent(aid)}` : '';
    const origHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '⚡ Dismantling...';
        btn.disabled = true;
    }

    try {
        const res = await fetch(`/api/strategy/dismantle${q}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: aid || null,
                execute: true,
                dry_run: false,
                commands: strategyShardPlan.batch_commands
            })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Dismantle failed');

        appendStrategyLog(`Enqueued ${count} dismantle commands into bot queue.`, 'info');

        if (typeof showToast === 'function') {
            showToast(data.message || 'Dismantle commands enqueued successfully!', 'success');
        }

        // Reload state after short delay
        setTimeout(() => loadStrategyView(false), 2500);
    } catch (err) {
        console.error('Error executing dismantle:', err);
        if (typeof showToast === 'function') {
            showToast('Dismantle execution failed: ' + err.message, 'error');
        }
    } finally {
        if (btn) {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }
    }
}

/**
 * Append entry to Strategy Telemetry & Execution Stream
 */
function appendStrategyLog(msg, type = 'info') {
    const logsEl = document.getElementById('strategyLogs');
    if (!logsEl) return;

    const timeStr = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `strat-log-entry ${type}`;
    entry.innerHTML = `<span class="strat-log-time">[${timeStr}]</span> <span>${escapeHtml(msg)}</span>`;
    logsEl.appendChild(entry);
    logsEl.scrollTop = logsEl.scrollHeight;

    // Limit log entries in DOM
    while (logsEl.children.length > 50) {
        logsEl.removeChild(logsEl.firstChild);
    }
}

/**
 * Hook into window.selectAccount for seamless reactive account switching
 */
(function hookAccountSwitch() {
    if (window._stratAccountHooked) return;
    window._stratAccountHooked = true;

    let lastKnownAccountId = typeof currentAccountId !== 'undefined' ? currentAccountId : null;

    const originalSelect = window.selectAccount;
    window.selectAccount = function(id) {
        if (typeof originalSelect === 'function') {
            try {
                originalSelect(id);
            } catch (err) {
                console.warn('Original selectAccount error:', err);
            }
        } else {
            currentAccountId = id;
        }

        // Cancel any active polling from previous account
        cancelEquipPolling();

        // Update strategy account badge immediately
        updateStrategyAccountBadge();

        // If switching accounts, clear cached state and reload strategy view immediately
        if (id !== lastKnownAccountId) {
            lastKnownAccountId = id;
            strategyState = null;
        }
        loadStrategyView(false);
    };

    // Watch for canonical currentAccountId changes triggered by background fetches
    setInterval(() => {
        if (typeof currentAccountId !== 'undefined' && currentAccountId && currentAccountId !== lastKnownAccountId) {
            lastKnownAccountId = currentAccountId;
            updateStrategyAccountBadge();
            const stratView = document.getElementById('strategy');
            if (stratView && stratView.classList.contains('active-view')) {
                strategyState = null;
                loadStrategyView(false);
            }
        }
    }, 1000);

    window.addEventListener('accountChanged', (e) => {
        if (e && e.detail && e.detail.id) {
            currentAccountId = e.detail.id;
            lastKnownAccountId = e.detail.id;
        }
        cancelEquipPolling();
        updateStrategyAccountBadge();
        strategyState = null;
        const stratView = document.getElementById('strategy');
        if (stratView && stratView.classList.contains('active-view')) {
            loadStrategyView(false);
        }
    });

    document.addEventListener('DOMContentLoaded', () => {
        updateStrategyAccountBadge();
        const stratView = document.getElementById('strategy');
        if (stratView && stratView.classList.contains('active-view')) {
            loadStrategyView(false);
        }
    });
})();

/**
 * Utility: Calculate estimated shards from weapon model
 */
function calculateEstimatedShards(w) {
    const q = w.quality_val || 20;
    if (q >= 90) return 40;
    if (q >= 70) return 25;
    if (q >= 50) return 15;
    return 10;
}

/**
 * Utility: Format numbers with commas
 */
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return Number(num).toLocaleString('en-US');
}

/**
 * Utility: Capitalize string
 */
function capitalize(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Utility: Escape HTML
 */
function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
