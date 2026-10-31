// ==========================================================================
// BRIGHTLOOP PUBLIC WEBSITE & SHOWCASE INTERACTIONS
// Phase 12: Premium Landing Page, Hero & ThreeUI Integration
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
  initBrandIntro3D();
  initNavbarScroll();
  initMobileMenu();
  initHeroVideo();
  initShowcaseTabs();
  initThreeUIScene();
});

// 0. 3D Geometric Brand Intro Screen Overlay (Three.js)
function initBrandIntro3D() {
  const overlay = document.getElementById('brand-intro-overlay');
  if (!overlay) return;

  const canvas = document.getElementById('brand-intro-canvas');
  const wordmark = document.getElementById('intro-wordmark');
  const subtext = document.getElementById('intro-subtext');
  const skipBtn = document.getElementById('skip-intro-btn');

  // Check if already seen in current session or user prefers reduced motion
  const alreadySeen = sessionStorage.getItem('brightloop_intro_seen');
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (alreadySeen || prefersReducedMotion) {
    overlay.style.display = 'none';
    return;
  }

  let animationFrameId = null;
  let renderer = null;
  let scene = null;
  let isDismissed = false;

  const dismissIntro = () => {
    if (isDismissed) return;
    isDismissed = true;
    sessionStorage.setItem('brightloop_intro_seen', 'true');
    overlay.classList.add('fade-out');

    setTimeout(() => {
      overlay.style.display = 'none';
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
      if (renderer) {
        renderer.dispose();
      }
    }, 850);
  };

  if (skipBtn) {
    skipBtn.addEventListener('click', dismissIntro);
  }

  // If Three.js is not loaded, gracefully fallback
  if (typeof THREE === 'undefined' || !canvas) {
    if (wordmark) wordmark.classList.add('reveal');
    if (subtext) subtext.classList.add('reveal');
    setTimeout(dismissIntro, 2000);
    return;
  }

  try {
    const width = window.innerWidth;
    const height = window.innerHeight;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x11120f); // Obsidian

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 18;

    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const goldLight1 = new THREE.DirectionalLight(0xc6a66b, 2.5); // Champagne Gold
    goldLight1.position.set(10, 15, 10);
    scene.add(goldLight1);

    const goldLight2 = new THREE.DirectionalLight(0xe8d5a8, 1.5); // Pale Gold
    goldLight2.position.set(-10, -10, 10);
    scene.add(goldLight2);

    const pointLight = new THREE.PointLight(0xc6a66b, 3, 50);
    pointLight.position.set(0, 0, 8);
    scene.add(pointLight);

    // 4 Geometric Interlocking Meshes (representing the 4 pillars of Brightloop)
    const goldMaterial = new THREE.MeshStandardMaterial({
      color: 0xc6a66b,
      metalness: 0.85,
      roughness: 0.25,
      wireframe: false,
    });

    const paleGoldMaterial = new THREE.MeshStandardMaterial({
      color: 0xe8d5a8,
      metalness: 0.9,
      roughness: 0.2,
      wireframe: false,
    });

    const geometries = [
      new THREE.TorusGeometry(3.6, 0.28, 16, 80, Math.PI * 1.2),
      new THREE.TorusGeometry(3.6, 0.28, 16, 80, Math.PI * 1.2),
      new THREE.TorusGeometry(2.2, 0.22, 16, 60, Math.PI * 1.5),
      new THREE.OctahedronGeometry(1.2, 0),
    ];

    const pieces = [];
    const targetTransforms = [
      { pos: new THREE.Vector3(0, 0, 0), rot: new THREE.Vector3(0, 0, 0) },
      { pos: new THREE.Vector3(0, 0, 0), rot: new THREE.Vector3(Math.PI, 0, Math.PI / 2) },
      { pos: new THREE.Vector3(0, 0, 0.5), rot: new THREE.Vector3(Math.PI / 4, Math.PI / 4, 0) },
      { pos: new THREE.Vector3(0, 0, 0), rot: new THREE.Vector3(0, 0, 0) },
    ];

    const startOffsets = [
      { x: -14, y: 10, z: -8, rx: 2, ry: -3, rz: 1 },
      { x: 14, y: -10, z: -6, rx: -2, ry: 3, rz: -1 },
      { x: -8, y: -12, z: -10, rx: 1, ry: -2, rz: 2 },
      { x: 0, y: 15, z: 5, rx: 3, ry: 2, rz: -2 },
    ];

    geometries.forEach((geom, idx) => {
      const mat = (idx % 2 === 0) ? goldMaterial : paleGoldMaterial;
      const mesh = new THREE.Mesh(geom, mat);
      const start = startOffsets[idx];
      mesh.position.set(start.x, start.y, start.z);
      mesh.rotation.set(start.rx, start.ry, start.rz);
      scene.add(mesh);
      pieces.push({ mesh, start, target: targetTransforms[idx] });
    });

    const startTime = performance.now();
    const convergenceDuration = 2200; // ms

    // Reveal typography halfway through convergence
    setTimeout(() => {
      if (wordmark) wordmark.classList.add('reveal');
      if (subtext) subtext.classList.add('reveal');
    }, 1100);

    // Auto-dismiss after sequence finishes
    setTimeout(dismissIntro, 3400);

    const onResize = () => {
      if (!renderer || isDismissed) return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener('resize', onResize);

    const animate = (now) => {
      if (isDismissed) return;
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / convergenceDuration, 1.0);
      const ease = 1 - Math.pow(1 - progress, 3);

      pieces.forEach(p => {
        p.mesh.position.x = p.start.x + (p.target.pos.x - p.start.x) * ease;
        p.mesh.position.y = p.start.y + (p.target.pos.y - p.start.y) * ease;
        p.mesh.position.z = p.start.z + (p.target.pos.z - p.start.z) * ease;

        p.mesh.rotation.x = p.start.rx + (p.target.rot.x - p.start.rx) * ease + elapsed * 0.0003;
        p.mesh.rotation.y = p.start.ry + (p.target.rot.y - p.start.ry) * ease + elapsed * 0.0005;
        p.mesh.rotation.z = p.start.rz + (p.target.rot.z - p.start.rz) * ease;
      });

      if (progress >= 1.0) {
        scene.rotation.y += 0.005;
        scene.rotation.x = Math.sin(now * 0.001) * 0.1;
      }

      renderer.render(scene, camera);
      animationFrameId = requestAnimationFrame(animate);
    };

    animationFrameId = requestAnimationFrame(animate);
  } catch (e) {
    console.warn('[Brightloop] 3D Intro WebGL fallback:', e);
    if (wordmark) wordmark.classList.add('reveal');
    if (subtext) subtext.classList.add('reveal');
    setTimeout(dismissIntro, 2000);
  }
}

// 1. Dynamic Navbar Scroll Effect
function initNavbarScroll() {
  const navbar = document.getElementById('navbar') || document.getElementById('main-navbar');
  if (!navbar) return;

  const handleScroll = () => {
    if (window.scrollY > 40) {
      navbar.classList.add('navbar-scrolled');
    } else {
      navbar.classList.remove('navbar-scrolled');
    }
  };

  window.addEventListener('scroll', handleScroll, { passive: true });
  handleScroll();
}

// 2. Mobile Menu Toggle
function initMobileMenu() {
  const toggleBtn = document.getElementById('mobile-menu-toggle');
  const menu = document.getElementById('mobile-nav-drawer') || document.querySelector('.nav-menu');
  if (!toggleBtn || !menu) return;

  toggleBtn.addEventListener('click', () => {
    const isOpen = menu.classList.toggle('open');
    toggleBtn.setAttribute('aria-expanded', isOpen);
    document.body.style.overflow = isOpen ? 'hidden' : '';
  });

  const links = menu.querySelectorAll('a');
  links.forEach(l => l.addEventListener('click', () => {
    menu.classList.remove('open');
    document.body.style.overflow = '';
  }));
}

// 3. Hero Video Configuration & Fallback
function initHeroVideo() {
  const video = document.getElementById('hero-video') || document.getElementById('palomar-hero-video');
  const fallback = document.getElementById('hero-video-fallback');
  if (!video) return;

  const playPromise = video.play();
  if (playPromise !== undefined) {
    playPromise.catch(err => {
      console.warn('[Brightloop] Autoplay was restrained or media failed:', err);
      if (fallback) fallback.style.display = 'block';
    });
  }

  video.addEventListener('error', () => {
    console.warn('[Brightloop] Hero video failed to load. Showing fallback.');
    if (fallback) fallback.style.display = 'block';
  });
}

// 4. Interactive Product Showcase Tabs
function initShowcaseTabs() {
  const tabs = document.querySelectorAll('.tab-trigger, .showcase-tab-btn');
  if (!tabs.length) return;

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetId = tab.dataset.tabTarget || tab.dataset.target;
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content-panel, .showcase-tab-content').forEach(c => c.classList.remove('active'));

      tab.classList.add('active');
      const target = document.getElementById(targetId);
      if (target) target.classList.add('active');
    });
  });
}

// 5. ThreeUI Interactive Particle/Shader Scene (Living Champagne Ambient Canvas)
function initThreeUIScene() {
  const canvas = document.getElementById('ambient-canvas') || document.getElementById('threeui-hero-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  let width = (canvas.width = window.innerWidth);
  let height = (canvas.height = window.innerHeight);

  const resize = () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  };
  window.addEventListener('resize', resize, { passive: true });

  // Luxury Champagne Gold Palette Particles
  const PARTICLE_COUNT = Math.min(50, Math.floor(width / 25));
  const particles = [];
  const colors = ['#C6A66B', '#E8D5A8', '#927344', '#F4EBDD'];

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      radius: Math.random() * 2.2 + 0.8,
      color: colors[Math.floor(Math.random() * colors.length)],
      alpha: Math.random() * 0.4 + 0.15,
      pulseSpeed: Math.random() * 0.02 + 0.01,
      angle: Math.random() * Math.PI * 2,
    });
  }

  let animationFrameId;
  function render() {
    ctx.clearRect(0, 0, width, height);

    // Update and draw living champagne ambient particles
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      p.angle += p.pulseSpeed;

      // Wrap around bounds
      if (p.x < 0) p.x = width;
      if (p.x > width) p.x = 0;
      if (p.y < 0) p.y = height;
      if (p.y > height) p.y = 0;

      const dynamicAlpha = p.alpha + Math.sin(p.angle) * 0.1;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = p.color;
      ctx.globalAlpha = Math.max(0.05, Math.min(dynamicAlpha, 0.6));
      ctx.fill();
    });

    // Draw gentle connection lines for nearby nodes (mesh matrix)
    ctx.globalAlpha = 0.06;
    ctx.strokeStyle = '#C6A66B';
    ctx.lineWidth = 0.8;

    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 120) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }

    ctx.globalAlpha = 1.0;
    animationFrameId = requestAnimationFrame(render);
  }

  render();
}
