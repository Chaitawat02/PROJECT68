import * as THREE from 'three';
import { GLTFLoader } from 'GLTFLoader.js';
import { MindARThree } from 'mindar-image-three.js';

const loadGLTF = (path) => {
    return new Promise((resolve) => {
        const loader = new GLTFLoader();
        loader.load(path, (gltf) => {
            resolve(gltf);
        });
    });
};

document.addEventListener("DOMContentLoaded", async () => {

    const mindarThree = new MindARThree({
        container: document.body,
        imageTargetSrc: "/static/main/targets/targets.mind",
        maxTrack: 7,
    });

    const { renderer, scene, camera } = mindarThree;

    const light = new THREE.HemisphereLight(0xffffff, 0xbbbbff, 1);
    scene.add(light);

    const models = [];

    for (let i = 0; i <= 6; i++) {
        const model = await loadGLTF(
            `/static/main/models/thai_silk_pattern_${i}.glb`
        );
        model.scene.scale.set(0.1, 0.1, 0.1);
        model.scene.position.set(0, -0.5, 0);
        models.push(model);
    }

    models.forEach((model, index) => {
        const anchor = mindarThree.addAnchor(index);
        anchor.group.add(model.scene);
    });

    await mindarThree.start();

    renderer.setAnimationLoop(() => {
        renderer.render(scene, camera);
    });
});
