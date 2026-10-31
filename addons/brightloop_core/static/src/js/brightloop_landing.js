// ==========================================================================
// BRIGHTLOOP PUBLIC WEBSITE & SHOWCASE INTERACTIONS
// Phase 12: Premium Landing Page, Hero & ThreeUI Integration
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
  initNavbarScroll();
  initMobileMenu();
  initHeroVideo();
  initShowcaseTabs();
  initThreeUIScene();
});

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

// 5. ThreeUI Interactive Particle/Shader Scene (Living Green Ambient Canvas)
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

  // Forest & Sage Palette Particles
  const PARTICLE_COUNT = Math.min(50, Math.floor(width / 25));
  const particles = [];
  const colors = ['#2D7A4F', '#4E9B6E', '#6BBF8A', '#D4AF37'];

  for (let i = 0; i < PARTICLE_COUNT; i++) {
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
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

    // Update and draw living green ambient particles
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
    ctx.strokeStyle = '#6BBF8A';
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
