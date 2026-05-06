class ParticleSystem {
    constructor() {
        this.container = document.getElementById('canvas-container');
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.particles = null;
        this.geometry = null;
        this.count = 15000;
        this.scroll = 0;

        this.init();
    }

    init() {
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.container.appendChild(this.renderer.domElement);

        this.camera.position.z = 5;

        this.createParticles();
        this.addEventListeners();
        this.animate();
    }

    createParticles() {
        this.geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(this.count * 3);
        const spreadPositions = new Float32Array(this.count * 3);
        const colors = new Float32Array(this.count * 3);
        const sizes = new Float32Array(this.count);

        const color1 = new THREE.Color('#4a90e2'); // Bright Blue
        const color2 = new THREE.Color('#ff6b6b'); // Coral Pink
        const color3 = new THREE.Color('#50c878'); // Emerald

        for (let i = 0; i < this.count; i++) {
            // Sphere Shape (Base)
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos((Math.random() * 2) - 1);
            const radius = 2 + (Math.random() * 0.5 - 0.25); // Slight thickness

            const x = radius * Math.sin(phi) * Math.cos(theta);
            const y = radius * Math.sin(phi) * Math.sin(theta);
            const z = radius * Math.cos(phi);

            positions[i * 3] = x;
            positions[i * 3 + 1] = y;
            positions[i * 3 + 2] = z;

            // Spread Positions
            spreadPositions[i * 3] = (Math.random() - 0.5) * 20;
            spreadPositions[i * 3 + 1] = (Math.random() - 0.5) * 20;
            spreadPositions[i * 3 + 2] = (Math.random() - 0.5) * 20;

            // Colors based on position
            const mixedColor = color1.clone();
            mixedColor.lerp(color2, (x + 2) / 4);
            mixedColor.lerp(color3, (y + 2) / 4);

            colors[i * 3] = mixedColor.r;
            colors[i * 3 + 1] = mixedColor.g;
            colors[i * 3 + 2] = mixedColor.b;

            sizes[i] = Math.random() * 0.05;
        }

        this.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        this.geometry.setAttribute('spreadPosition', new THREE.BufferAttribute(spreadPositions, 3));
        this.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        this.geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

        const material = new THREE.PointsMaterial({
            size: 0.02,
            vertexColors: true,
            transparent: true,
            opacity: 0.6,
            blending: THREE.NormalBlending,
            sizeAttenuation: true
        });

        this.particles = new THREE.Points(this.geometry, material);
        this.scene.add(this.particles);
    }

    addEventListeners() {
        window.addEventListener('scroll', () => {
            this.scroll = window.scrollY / (document.documentElement.scrollHeight - window.innerHeight);
        });

        window.addEventListener('resize', () => {
            this.camera.aspect = window.innerWidth / window.innerHeight;
            this.camera.updateProjectionMatrix();
            this.renderer.setSize(window.innerWidth, window.innerHeight);
        });
    }

    update() {
        const positions = this.geometry.attributes.position.array;
        const basePositions = this.geometry.attributes.position.array; // We need to store base somewhere or use another attr
        // Re-creating or using attributes for transitions
        // For efficiency in a real app, I'd use a shader. For this task, I'll use a custom attribute logic.
        
        // Let's use a simpler approach: update the mesh's position/scale or use GSAP for the transition
        // But for 15k particles, CPU updates are slow. Let's use a shader-like approach in the update loop or just GSAP on a uniform.
    }

    animate() {
        requestAnimationFrame(this.animate.bind(this));

        const time = Date.now() * 0.0005;
        this.particles.rotation.y = time * 0.1;
        this.particles.rotation.x = time * 0.05;

        // Reactive scroll transition
        const positions = this.geometry.attributes.position.array;
        const spreadPos = this.geometry.attributes.spreadPosition.array;
        
        // We need the original sphere positions. Let's store them.
        if (!this.basePositions) {
            this.basePositions = new Float32Array(positions);
        }

        for (let i = 0; i < this.count; i++) {
            const i3 = i * 3;
            // Interpolate between base and spread
            // Using a smooth easing for scroll
            const targetX = THREE.MathUtils.lerp(this.basePositions[i3], spreadPos[i3], this.scroll);
            const targetY = THREE.MathUtils.lerp(this.basePositions[i3+1], spreadPos[i3+1], this.scroll);
            const targetZ = THREE.MathUtils.lerp(this.basePositions[i3+2], spreadPos[i3+2], this.scroll);

            // Add some "noise" or movement
            positions[i3] += (targetX - positions[i3]) * 0.1;
            positions[i3+1] += (targetY - positions[i3+1]) * 0.1;
            positions[i3+2] += (targetZ - positions[i3+2]) * 0.1;
        }
        
        this.geometry.attributes.position.needsUpdate = true;

        this.renderer.render(this.scene, this.camera);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    new ParticleSystem();
});
