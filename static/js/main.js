class ParticleSystem {
    constructor() {
        this.container = document.getElementById('canvas-container');
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        this.renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true }); // Disabled antialias for performance
        this.particles = null;
        this.geometry = null;
        this.count = 8000; // Reduced count for better performance
        this.scroll = 0;
        this.targetScroll = 0;

        this.init();
    }

    init() {
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5)); // Capped pixel ratio
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
        const opacities = new Float32Array(this.count);
        const randomOffsets = new Float32Array(this.count);

        const googleColors = ['#4285F4', '#EA4335', '#FBBC05', '#34A853', '#8E24AA'];

        for (let i = 0; i < this.count; i++) {
            const i3 = i * 3;
            // Sphere Shape
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos((Math.random() * 2) - 1);
            const radius = 2 + (Math.random() * 0.4 - 0.2);

            positions[i3] = radius * Math.sin(phi) * Math.cos(theta);
            positions[i3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
            positions[i3 + 2] = radius * Math.cos(phi);

            // Spread Positions (Larger range)
            spreadPositions[i3] = (Math.random() - 0.5) * 30;
            spreadPositions[i3 + 1] = (Math.random() - 0.5) * 30;
            spreadPositions[i3 + 2] = (Math.random() - 0.5) * 30;

            const randomColor = new THREE.Color(googleColors[Math.floor(Math.random() * googleColors.length)]);
            colors[i3] = randomColor.r;
            colors[i3 + 1] = randomColor.g;
            colors[i3 + 2] = randomColor.b;

            opacities[i] = 1.0;
            randomOffsets[i] = Math.random(); // Used for "smart" staggered disappearance
        }

        this.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        this.geometry.setAttribute('spreadPosition', new THREE.BufferAttribute(spreadPositions, 3));
        this.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        this.geometry.setAttribute('opacity', new THREE.BufferAttribute(opacities, 1));
        this.geometry.setAttribute('randomOffset', new THREE.BufferAttribute(randomOffsets, 1));

        // Using a simpler material for better performance
        this.material = new THREE.PointsMaterial({
            size: 0.025,
            vertexColors: true,
            transparent: true,
            opacity: 1.0,
            sizeAttenuation: true
        });

        this.particles = new THREE.Points(this.geometry, this.material);
        this.scene.add(this.particles);
        
        this.basePositions = new Float32Array(positions);
    }

    addEventListeners() {
        window.addEventListener('scroll', () => {
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
        this.scroll += (this.targetScroll - this.scroll) * 0.05;

        const time = Date.now() * 0.0005;
        this.particles.rotation.y = time * 0.1;

        const posAttr = this.geometry.attributes.position.array;
        const spreadAttr = this.geometry.attributes.spreadPosition.array;
        const opacAttr = this.geometry.attributes.opacity.array;
        const offsetAttr = this.geometry.attributes.randomOffset.array;

        for (let i = 0; i < this.count; i++) {
            const i3 = i * 3;
            const offset = offsetAttr[i];
            
            // "Smart" Fade logic: Particles disappear at different rates based on their random offset
            // As scroll increases, particles with lower offsets fade out first
            const fadeThreshold = this.scroll * 1.5; 
            const particleOpacity = Math.max(0, 1 - (fadeThreshold - offset * 0.5));
            opacAttr[i] = particleOpacity;

            // Only update position if particle is somewhat visible
            if (particleOpacity > 0.01) {
                posAttr[i3] = THREE.MathUtils.lerp(this.basePositions[i3], spreadAttr[i3], this.scroll);
                posAttr[i3+1] = THREE.MathUtils.lerp(this.basePositions[i3+1], spreadAttr[i3+1], this.scroll);
                posAttr[i3+2] = THREE.MathUtils.lerp(this.basePositions[i3+2], spreadAttr[i3+2], this.scroll);
            }
        }
        
        this.geometry.attributes.position.needsUpdate = true;
        this.geometry.attributes.opacity.needsUpdate = true;

        this.renderer.render(this.scene, this.camera);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new ParticleSystem();
});
