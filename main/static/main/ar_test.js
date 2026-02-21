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
    const statusText = document.getElementById("status-text");
    const loaderScreen = document.getElementById("app-loader");

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

    // ค่าเริ่มต้น:
    // - Desktop: กล้องหน้า (user) ให้เหมือนกระจก
    // - Mobile / Tablet: กล้องหลัง (environment) เพื่อสแกนเป้าได้สะดวก
    let facingMode = isMobile ? "environment" : "user";

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
    // Loop through data and set up anchors immediately
    patternsData.forEach((pattern, index) => {
        const anchor = mindarThree.addAnchor(index);

        // --- Logic A: Model Loading (Async) ---
        // Construct URL: Use field from DB or fallback to pattern_X.glb
        let modelUrl = pattern.silk_model_url || pattern.model_url;
        if (!modelUrl) {
            // Fallback convention
            modelUrl = `${modelBase}thai_silk_pattern_${index}.glb`; 
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
                console.warn(`Failed to load model for index ${index}: ${modelUrl}`, err);
            });

        // --- Logic B: UI Updates on Target Found ---
        anchor.onTargetFound = () => {
            // Update Text
            if (displayTitle) displayTitle.innerText = pattern.name || "Silk Pattern " + (index + 1);
            if (displayDesc) displayDesc.innerText = pattern.detail || "Luxury Thai Silk Collection";
            
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

            // Update Full Detail List (หลังจากสแกน AR แสดงข้อมูลทั้งหมดให้อ่านง่าย)
            if (displayMeta) {
                const rows = [];
                if (pattern.si_id) {
                    rows.push(`<div class="meta-row"><span class="meta-label">รหัสผ้า:</span><span class="meta-value">${pattern.si_id}</span></div>`);
                }
                if (pattern.si_type) {
                    rows.push(`<div class="meta-row"><span class="meta-label">ประเภทผ้า:</span><span class="meta-value">${pattern.si_type}</span></div>`);
                }
                if (pattern.si_color) {
                    rows.push(`<div class="meta-row"><span class="meta-label">สีหลัก:</span><span class="meta-value">${pattern.si_color}</span></div>`);
                }
                if (pattern.si_address) {
                    rows.push(`<div class="meta-row"><span class="meta-label">แหล่งผลิต / ที่มา:</span><span class="meta-value">${pattern.si_address}</span></div>`);
                }
                if (pattern.target_file) {
                    rows.push(`<div class="meta-row"><span class="meta-label">Target File:</span><span class="meta-value">${pattern.target_file}</span></div>`);
                }
                if (pattern.si_history) {
                    rows.push(`<div class="meta-block"><span class="meta-label">ประวัติความเป็นมา</span><p class="meta-value">${pattern.si_history}</p></div>`);
                }

                displayMeta.innerHTML = rows.join("");
                displayMeta.classList.remove("hidden");
            }

            // Update Status Badge
            if (statusText) {
                statusText.innerText = "Pattern Detected";
                statusText.style.color = "#2ecc71"; // Green
                // Animate dot if needed
                const dot = document.querySelector('.status-dot');
                if(dot) dot.style.backgroundColor = "#2ecc71";
            }
        };

        anchor.onTargetLost = () => {
             if (statusText) {
                statusText.innerText = "Scanning...";
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
        if (loaderScreen) {
            loaderScreen.innerHTML = `<div style="color:red; text-align:center; padding:20px;">
                <h3>Camera Error</h3>
                <p>Please allow camera access or try a different browser.</p>
                <p><small>${err.message}</small></p>
            </div>`;
        }
    }
});