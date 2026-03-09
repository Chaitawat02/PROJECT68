import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MindARThree } from "mindar-image-three";

// Helper: Load GLTF
const loadGLTF = (path) => {
    return new Promise((resolve, reject) => {
        const loader = new GLTFLoader();
        loader.load(path, (gltf) => resolve(gltf), undefined, (err) => reject(err));
    });
};

document.addEventListener("DOMContentLoaded", async () => {
    // 1. UI Elements References
    const displayTitle = document.getElementById("panel-name");
    const displayDesc = document.getElementById("panel-sub");
    const displayImg = document.getElementById("panel-image");
    const displayMeta = document.getElementById("panel-meta");
    const displaySummary = document.getElementById("panel-summary");
    const statusText = document.getElementById("status-text");
    const loaderScreen = document.getElementById("app-loader");

    // Info pages (1: name, 2: images, 3: details)
    const infoPanel = document.getElementById("info-panel");
    const infoNav = document.getElementById("info-nav");
    const infoNavButtons = Array.from(document.querySelectorAll(".info-nav-btn[data-info-page]"));
    const infoPages = Array.from(document.querySelectorAll(".info-page[data-page]"));
    const galleryEl = document.getElementById("panel-gallery");
    const galleryEmptyEl = document.getElementById("panel-gallery-empty");

    const TOTAL_INFO_PAGES = 3;
    let currentInfoPage = 1;

    const setInfoPage = (page) => {
        const next = Math.max(1, Math.min(TOTAL_INFO_PAGES, Number(page) || 1));
        currentInfoPage = next;

        if (infoPanel) infoPanel.dataset.infoPage = String(next);

        infoPages.forEach((el) => {
            const p = Number(el.getAttribute("data-page"));
            if (p === next) el.classList.add("is-active");
            else el.classList.remove("is-active");
        });

        infoNavButtons.forEach((btn) => {
            const p = Number(btn.getAttribute("data-info-page"));
            const active = p === next;
            btn.classList.toggle("is-active", active);
            btn.setAttribute("aria-pressed", active ? "true" : "false");
        });
    };

    const setInfoNavVisible = (visible) => {
        if (!infoNav) return;
        if (visible) infoNav.classList.remove("hidden");
        else infoNav.classList.add("hidden");
    };

    const toText = (value) => {
        if (value === null || value === undefined) return "";
        return String(value).trim();
    };

    const clearChildren = (el) => {
        if (!el) return;
        while (el.firstChild) el.removeChild(el.firstChild);
    };

    const addRow = (rootEl, label, value) => {
        if (!rootEl) return;
        const v = toText(value);
        if (!v) return;

        const row = document.createElement("div");
        row.className = "meta-row";

        const labelEl = document.createElement("span");
        labelEl.className = "meta-label";
        labelEl.textContent = label;

        const valueEl = document.createElement("span");
        valueEl.className = "meta-value";
        valueEl.textContent = v;

        row.appendChild(labelEl);
        row.appendChild(valueEl);
        rootEl.appendChild(row);
    };

    const addBlock = (rootEl, label, value) => {
        if (!rootEl) return;
        const v = toText(value);
        if (!v) return;

        const block = document.createElement("div");
        block.className = "meta-block";

        const labelEl = document.createElement("span");
        labelEl.className = "meta-label";
        labelEl.textContent = label;

        const valueEl = document.createElement("div");
        valueEl.className = "meta-value meta-preline";
        valueEl.textContent = v;

        block.appendChild(labelEl);
        block.appendChild(valueEl);
        rootEl.appendChild(block);
    };

    const setGalleryImages = (urls) => {
        if (!galleryEl || !galleryEmptyEl) return;

        while (galleryEl.firstChild) galleryEl.removeChild(galleryEl.firstChild);

        const list = Array.from(new Set((Array.isArray(urls) ? urls : []).map(String).map((s) => s.trim()).filter(Boolean)));
        if (!list.length) {
            galleryEmptyEl.classList.remove("hidden");
            return;
        }

        galleryEmptyEl.classList.add("hidden");
        list.forEach((src) => {
            const img = document.createElement("img");
            img.className = "gallery-img";
            img.src = src;
            img.alt = "Silk image";
            img.loading = "lazy";
            galleryEl.appendChild(img);
        });
    };

    // Bind nav events (3-tab buttons)
    infoNavButtons.forEach((btn) => {
        btn.addEventListener("click", () => setInfoPage(btn.getAttribute("data-info-page")));
    });
    setInfoPage(1);
    setInfoNavVisible(false);

    // Reset global flags used by the outer page auto-cycling
    try {
        window.__arDetected = false;
        window.__arDetectedAt = 0;
        window.__arLostAt = 0;
        window.__arStartFailed = false;
    } catch (e) {
        // ignore
    }

    // If there are multiple target files, we will auto-cycle in the outer page.
    // Keep the status message friendly while scanning.
    const mindSelectForStatus = document.getElementById("mindSelect");
    const hasMultipleMindFiles = (() => {
        if (!mindSelectForStatus || !mindSelectForStatus.options) return false;
        const files = Array.from(mindSelectForStatus.options)
            .map((o) => (o && o.value ? String(o.value).trim() : ""))
            .filter(Boolean);
        const uniqueFiles = Array.from(new Set(files));
        return uniqueFiles.length > 1;
    })();
    if (statusText && hasMultipleMindFiles) {
        statusText.innerText = "กำลังค้นหาลายผ้า... รอหน่อยนะ";
    }

    // 2. Load Data from DOM (Django Template Injection)
    let patternsData = [];
    const patternsEl = document.getElementById("patterns-data");
    if (patternsEl && patternsEl.textContent.trim()) {
        try {
            patternsData = JSON.parse(patternsEl.textContent);
        } catch (e) {
            console.error("JSON Parse Error:", e);
        }
    }

    // Get Base Paths
    const targetsEl = document.getElementById("targets-url");
    let targetsUrl = targetsEl ? JSON.parse(targetsEl.textContent) : "";
    
    const container = document.querySelector("#ar-root");
    const modelBase = container.getAttribute("data-model-base") || "/static/main/models/";

    // 3. Camera mode (front/back) from URL + device type
    const params = new URLSearchParams(window.location.search);
    const camParam = params.get("cam");

    // ตรวจว่าขณะนี้เป็นมือถือหรือแท็บเล็ตหรือไม่ (สำหรับกำหนดค่าเริ่มต้น)
    const isMobile = /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent) || window.innerWidth < 900;

    // 3.1 Mirror mode (หน้ากระจก): default เป็นกล้องหน้าแม้บนมือถือ
    // - ใช้ route /ar-mirror/ (มีใน urls.py) หรือ ?mode=mirror
    const isMirrorMode = (() => {
        try {
            const path = String(window.location.pathname || "");
            if (path.includes("/ar-mirror")) return true;
            const mode = params.get("mode");
            return mode === "mirror";
        } catch (e) {
            return false;
        }
    })();

    // ค่าเริ่มต้น:
    // - Desktop: กล้องหน้า (user) ให้เหมือนกระจก
    // - Mobile / Tablet: กล้องหลัง (environment) เพื่อสแกนเป้าได้สะดวก
    let facingMode = (isMirrorMode ? "user" : (isMobile ? "environment" : "user"));

    // ถ้ามี query ?cam=... ให้ใช้ตามที่ผู้ใช้เลือก
    if (camParam === "environment" || camParam === "back") {
        facingMode = "environment";
    } else if (camParam === "user" || camParam === "front") {
        facingMode = "user";
    }

    // Mirror only for front camera (remove mirroring on back camera)
    if (facingMode === "environment") {
        document.body.classList.add("no-mirror");
    } else {
        document.body.classList.remove("no-mirror");
    }

    // 4. Initialize MindAR with chosen camera
    const mindarThree = new MindARThree({
        container: container,
        imageTargetSrc: targetsUrl,
        maxTrack: 1, // Track 1 image at a time for performance
        filterMinCF: 0.0001, // Reduce jitter
        filterBeta: 0.001,
        videoSettings: {
            facingMode: { ideal: facingMode },
        },
    });

    const { renderer, scene, camera } = mindarThree;

    // 5. Lighting Setup (Optimized for Silk)
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;

    const ambientLight = new THREE.AmbientLight(0xffffff, 1.0);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.5);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);

    const backLight = new THREE.DirectionalLight(0xffffff, 0.8); // Rim light
    backLight.position.set(-5, 5, -5);
    scene.add(backLight);

    // 6. Setup Anchors & Models
    // IMPORTANT: Must use the SAME index as the .mind file (target order)
    // The backend provides `pattern.index` (mapped from DB target_index).
    patternsData.forEach((pattern, arrayIndex) => {
        const targetIndexRaw = (pattern && (pattern.index ?? pattern.target_index ?? pattern.source_index));
        const targetIndex = Number.isFinite(Number(targetIndexRaw)) ? Number(targetIndexRaw) : arrayIndex;

        if (!Number.isFinite(targetIndex) || targetIndex < 0) {
            console.warn("Invalid target index; skipping pattern", { pattern, arrayIndex });
            return;
        }

        const anchor = mindarThree.addAnchor(targetIndex);

        // --- Logic A: Model Loading (Async) ---
        // Construct URL: Use field from DB or fallback to pattern_X.glb
        let modelUrl = pattern.silk_model_url || pattern.model_url;
        if (!modelUrl) {
            // Fallback convention
            modelUrl = `${modelBase}thai_silk_pattern_${targetIndex}.glb`; 
        } else if (!modelUrl.startsWith('http') && !modelUrl.startsWith('/')) {
            // Append base if it's just a filename
            modelUrl = modelBase + modelUrl;
        }

        // Load model in background (don't block the camera start)
        loadGLTF(modelUrl)
            .then((gltf) => {
                const model = gltf.scene;

                // Adjust Model
                // ลดขนาดและถอยออกเล็กน้อย เพื่อให้รู้สึกว่าไม่ซูมเมื่อสแกนติด
                model.scale.set(0.85, 0.85, 0.85);
                model.position.set(0, -0.4, -0.6);

                // Fix: some exported .glb appear upside-down in MindAR scene
                // Apply a 180° roll so the model is upright.
                model.rotation.z = Math.PI;
                
                // Enable Shadows
                model.traverse((o) => {
                    if (o.isMesh) {
                        o.castShadow = true;
                        o.receiveShadow = true;
                        // Enhance material if needed
                        if(o.material) {
                            o.material.roughness = 0.4; // Silky look
                            o.material.metalness = 0.2;
                        }
                    }
                });

                anchor.group.add(model);
            })
            .catch((err) => {
                console.warn(`Failed to load model for index ${targetIndex}: ${modelUrl}`, err);
            });

        // --- Logic B: UI Updates on Target Found ---
        anchor.onTargetFound = () => {
            try {
                // Let the outer page know we detected something (used for auto-cycling mind files)
                window.__arDetected = true;
                window.__arDetectedAt = Date.now();
                window.__arLostAt = 0;

                // Persist last successful mind file for users who don't know what to pick
                const params = new URLSearchParams(window.location.search);
                const mindFromUrl = params.get("mind");
                const mindSelect = document.getElementById("mindSelect");
                const chosenMind = (mindFromUrl || (mindSelect && mindSelect.value) || "").trim();
                if (chosenMind) {
                    localStorage.setItem("ar_last_mind", chosenMind);
                }
            } catch (e) {
                // ignore
            }

            // Update Text
            if (displayTitle) displayTitle.innerText = pattern.name || "Silk Pattern " + (targetIndex + 1);
            if (displayDesc) {
                // ซ่อนบรรทัดตัวหนังสือจางๆ ใต้ชื่อ (เลี่ยงข้อมูลซ้ำกับกล่องด้านล่าง)
                displayDesc.innerText = "";
                displayDesc.classList.add("hidden");
            }
            
            // Update Image
            if (displayImg) {
                const imgUrl = pattern.image_url || pattern.image;
                if (imgUrl) {
                    displayImg.src = imgUrl;
                } else {
                    // Placeholder with text
                    displayImg.src = `https://placehold.co/400x400/EEE/999?text=${encodeURIComponent(pattern.name || 'Silk')}`;
                }
            }

            // Update Gallery (Page 2)
            try {
                const urls = Array.isArray(pattern.images) ? pattern.images : [];
                const fallback = pattern.image_url || pattern.image;
                const combined = [...urls];
                if (fallback) combined.unshift(fallback);
                setGalleryImages(combined);
            } catch (e) {
                setGalleryImages([]);
            }

            // Page 1: ข้อมูลผ้าไหม (ประเภท/สีหลัก)
            if (displaySummary) {
                clearChildren(displaySummary);
                addRow(displaySummary, "ประเภทผ้า:", pattern.si_type);
                addRow(displaySummary, "สีหลัก:", pattern.si_color);
                displaySummary.classList.remove("hidden");
            }

            // Page 2: แหล่งผลิต/ผู้คิดค้นลาย + ประวัติ
            if (displayMeta) {
                clearChildren(displayMeta);
                addRow(displayMeta, "แหล่งผลิต / ผู้คิดค้นลาย:", pattern.si_address);
                addBlock(displayMeta, "ประวัติความเป็นมา", pattern.si_history);
                displayMeta.classList.remove("hidden");
            }

            // Show info nav + reset to first page after detection
            setInfoNavVisible(true);
            setInfoPage(1);

            // Update Status Badge
            if (statusText) {
                statusText.innerText = "พบลายผ้าแล้ว";
                statusText.style.color = "#2ecc71"; // Green
                // Animate dot if needed
                const dot = document.querySelector('.status-dot');
                if(dot) dot.style.backgroundColor = "#2ecc71";
            }
        };

        anchor.onTargetLost = () => {
             // Allow auto-cycling to continue if detection was lost
             try {
                 window.__arDetected = false;
                 window.__arDetectedAt = 0;
                 window.__arLostAt = Date.now();
             } catch (e) {
                 // ignore
             }
             if (statusText) {
                statusText.innerText = hasMultipleMindFiles
                    ? "กำลังค้นหาลายผ้า... รอหน่อยนะ"
                    : "Scanning...";
                statusText.style.color = "#fff";
                
                const dot = document.querySelector('.status-dot');
                if(dot) dot.style.backgroundColor = "#f39c12"; // Orange/Gold
            }
        };
    });

    // 7. Start AR Engine
    try {
        await mindarThree.start();
        
        // --- Success: Start Loop & Remove Loader ---
        renderer.setAnimationLoop(() => {
            renderer.render(scene, camera);
        });

        // Hide Loading Screen smoothly
        if (loaderScreen) {
            loaderScreen.style.opacity = '0';
            setTimeout(() => loaderScreen.remove(), 600);
        }

    } catch (err) {
        console.error("Failed to start MindAR", err);
        try { window.__arStartFailed = true; } catch (e) {}
        if (loaderScreen) {
            loaderScreen.innerHTML = `<div style="color:red; text-align:center; padding:20px;">
                <h3>Camera Error</h3>
                <p>Please allow camera access or try a different browser.</p>
                <p><small>${err.message}</small></p>
            </div>`;
        }
    }
});