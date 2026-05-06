class ParticleSystem {
    constructor() {
        this.container = document.getElementById('canvas-container');
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        this.renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true }); // Performance: disabled antialias
        this.particles = null;
        this.geometry = null;
        this.count = 0;
        this.clock = new THREE.Clock();
        this.scroll = 0;
        this.targetScroll = 0;

        this.init();
    }

    init() {
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5)); // Capped for performance
        this.container.appendChild(this.renderer.domElement);

        this.camera.position.z = 4;

        this.createParticles();
        this.addEventListeners();
        this.animate();
    }

    createParticles() {
        // Create a structured sphere geometry
        // Segments slightly reduced from 128 to 100 for better performance when scattering
        const sphereGeom = new THREE.SphereGeometry(1.8, 100, 100);
        const basePositionsArray = sphereGeom.attributes.position.array;
        
        this.count = basePositionsArray.length / 3;
        
        this.geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(this.count * 3);
        const basePositions = new Float32Array(this.count * 3);
        const spreadPositions = new Float32Array(this.count * 3);
        const colors = new Float32Array(this.count * 3);
        const opacities = new Float32Array(this.count);
        const randomOffsets = new Float32Array(this.count);

        const colorTop = new THREE.Color('#38bdf8'); // Light Blue
        const colorBottom = new THREE.Color('#a855f7'); // Purple

        for (let i = 0; i < this.count; i++) {
            const i3 = i * 3;
            
            basePositions[i3] = basePositionsArray[i3];
            basePositions[i3 + 1] = basePositionsArray[i3 + 1];
            basePositions[i3 + 2] = basePositionsArray[i3 + 2];

            positions[i3] = basePositions[i3];
            positions[i3 + 1] = basePositions[i3 + 1];
            positions[i3 + 2] = basePositions[i3 + 2];

            // Scatter spread positions
            spreadPositions[i3] = (Math.random() - 0.5) * 40;
            spreadPositions[i3 + 1] = (Math.random() - 0.5) * 40;
            spreadPositions[i3 + 2] = (Math.random() - 0.5) * 40;
            
            // Gradient based on Y and X position
            const normalizedY = (basePositions[i3 + 1] + 1.8) / 3.6; // 0 to 1
            const normalizedX = (basePositions[i3] + 1.8) / 3.6; // 0 to 1
            const mixRatio = (normalizedY + (1 - normalizedX)) / 2;
            
            const color = new THREE.Color();
            color.lerpColors(colorBottom, colorTop, mixRatio);
            
            // Store the base colors to use later for fading
            colors[i3] = color.r;
            colors[i3 + 1] = color.g;
            colors[i3 + 2] = color.b;

            opacities[i] = 1.0;
            randomOffsets[i] = Math.random(); // Smart offset for fading
        }

        this.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        this.geometry.setAttribute('basePosition', new THREE.BufferAttribute(basePositions, 3));
        this.geometry.setAttribute('spreadPosition', new THREE.BufferAttribute(spreadPositions, 3));
        this.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        this.geometry.setAttribute('baseColor', new THREE.BufferAttribute(new Float32Array(colors), 3));
        this.geometry.setAttribute('opacity', new THREE.BufferAttribute(opacities, 1));
        this.geometry.setAttribute('randomOffset', new THREE.BufferAttribute(randomOffsets, 1));

        this.material = new THREE.PointsMaterial({
            size: 0.02,
            vertexColors: true,
            transparent: true,
            opacity: 1.0,
            sizeAttenuation: true
        });

        this.particles = new THREE.Points(this.geometry, this.material);
        
        // Tilt the sphere to get a nice angle
        this.particles.rotation.x = Math.PI / 6;
        this.particles.rotation.z = Math.PI / 8;
        
        this.scene.add(this.particles);
    }

    addEventListeners() {
        window.addEventListener('scroll', () => {
            // Calculate scroll progress (0 to 1)
            this.targetScroll = window.scrollY / (document.documentElement.scrollHeight - window.innerHeight);
        });

        window.addEventListener('resize', () => {
            this.camera.aspect = window.innerWidth / window.innerHeight;
            this.camera.updateProjectionMatrix();
            this.renderer.setSize(window.innerWidth, window.innerHeight);
        });
    }

    animate() {
        requestAnimationFrame(this.animate.bind(this));

        // Smooth scroll transition
        this.scroll += (this.targetScroll - this.scroll) * 0.08;

        const elapsedTime = this.clock.getElapsedTime();

        // Slow rotation (reduces when fully scattered to save visual chaos)
        this.particles.rotation.y = elapsedTime * 0.15 + (this.scroll * Math.PI * 0.5);
        this.camera.position.z = 4 + this.scroll * 3; // Zoom out slightly on scroll

        const posAttr = this.geometry.attributes.position;
        const baseAttr = this.geometry.attributes.basePosition;
        const spreadAttr = this.geometry.attributes.spreadPosition;
        const opacAttr = this.geometry.attributes.opacity;
        const offsetAttr = this.geometry.attributes.randomOffset;
        const colorAttr = this.geometry.attributes.color;
        const baseColorAttr = this.geometry.attributes.baseColor;

        // Three main frequency layers to create the complex undulating shape
        const t1 = elapsedTime * 0.5;
        const t2 = elapsedTime * 0.8;

        // Optimize: don't calculate complex waves if scroll is high (particles are scattered anyway)
        const calculateWaves = this.scroll < 0.8;

        for (let i = 0; i < this.count; i++) {
            const i3 = i * 3;
            const offset = offsetAttr.array[i];
            
            // "Smart" Fade logic: Particles scatter and become fainter, but don't disappear entirely
            // By capping the fade effect, we ensure they remain visible as a scattered background
            const fadeEffect = this.scroll * (0.5 + offset * 0.5); 
            const particleOpacity = Math.max(0.25, 1 - fadeEffect);
            opacAttr.array[i] = particleOpacity;

            // Fade to background color (#f0f4f8) to effectively fade out in light theme
            const bgR = 0.941; // 240 / 255
            const bgG = 0.957; // 244 / 255
            const bgB = 0.972; // 248 / 255
            
            colorAttr.array[i3] = THREE.MathUtils.lerp(bgR, baseColorAttr.array[i3], particleOpacity);
            colorAttr.array[i3 + 1] = THREE.MathUtils.lerp(bgG, baseColorAttr.array[i3 + 1], particleOpacity);
            colorAttr.array[i3 + 2] = THREE.MathUtils.lerp(bgB, baseColorAttr.array[i3 + 2], particleOpacity);

            // Always update positions since we want them visible
            let currentX = baseAttr.array[i3];
            let currentY = baseAttr.array[i3 + 1];
            let currentZ = baseAttr.array[i3 + 2];

            if (calculateWaves) {
                // Apply wave distortion to the base position
                let distortion = Math.sin(currentX * 2.5 + t1) * 0.15;
                distortion += Math.sin(currentY * 2.0 + t2) * 0.15;
                distortion += Math.sin(currentZ * 3.0 - t1) * 0.1;
                
                const len = Math.sqrt(currentX*currentX + currentY*currentY + currentZ*currentZ);
                currentX += (currentX / len) * distortion;
                currentY += (currentY / len) * distortion;
                currentZ += (currentZ / len) * distortion;
            }

            // Lerp between the wave position and the scattered position based on scroll
            posAttr.array[i3] = THREE.MathUtils.lerp(currentX, spreadAttr.array[i3], this.scroll);
            posAttr.array[i3 + 1] = THREE.MathUtils.lerp(currentY, spreadAttr.array[i3 + 1], this.scroll);
            posAttr.array[i3 + 2] = THREE.MathUtils.lerp(currentZ, spreadAttr.array[i3 + 2], this.scroll);
        }

        posAttr.needsUpdate = true;
        colorAttr.needsUpdate = true;
        this.renderer.render(this.scene, this.camera);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new ParticleSystem();
});
