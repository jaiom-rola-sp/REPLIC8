import { useEffect, useRef } from 'react';

const FAR_DEPTH = 1800;
const NEAR_DEPTH = 180;
const FOCAL_LENGTH = 760;
const MAX_SCROLL_SPEED = 6500;
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const smoothstep = (value) => value * value * (3 - 2 * value);

export default function Starfield({ reducedMotion = false }) {
  const canvasRef = useRef(null);
  const motionRef = useRef(reducedMotion);
  const resumeRef = useRef(null);
  motionRef.current = reducedMotion;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;

    let width = 1;
    let height = 1;
    let stars = [];
    let frame = 0;
    let previousTime = null;
    let elapsed = 0;
    let disposed = false;
    let seed = 821;
    let scrollVelocity = 0;
    let targetVelocity = 0;
    let previousScroll = window.scrollY;
    let previousScrollTime = performance.now();
    const pointer = { x: 0, y: 0 };
    const targetPointer = { x: 0, y: 0 };
    const warpStage = document.querySelector('[data-warp-stage]');
    const random = () => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
    const resetStar = (star, initial = false, backwards = false) => {
      star.z = initial
        ? 260 + random() * (FAR_DEPTH - 260)
        : backwards ? NEAR_DEPTH + 16 : FAR_DEPTH;
      // Uniform screen coverage preserves a dense field at every depth.
      star.x = (random() - 0.58) * (width + 40) * star.z / FOCAL_LENGTH;
      star.y = (random() - 0.46) * (height + 40) * star.z / FOCAL_LENGTH;
      star.radius = 0.27 + random() ** 3 * 1.02;
      star.alpha = 0.2 + random() * 0.65;
      star.phase = random() * Math.PI * 2;
      star.speed = 10 + random() * 13;
      star.square = random() > 0.91;
      return star;
    };

    const render = (delta = 0) => {
      ctx.clearRect(0, 0, width, height);
      // One geometry read per frame keeps the star tunnel aligned to the
      // silver loop's reticle while the portal enters and leaves the viewport.
      const portalBounds = warpStage?.getBoundingClientRect();
      const portalInfluence = portalBounds
        ? smoothstep(clamp((height - portalBounds.top) / height, 0, 1))
          * smoothstep(clamp(portalBounds.bottom / height, 0, 1))
        : 0;
      const centerX = width * (0.58 - portalInfluence * 0.08);
      const centerY = height * (0.46 + portalInfluence * 0.04);
      const scroll = window.scrollY;
      // Signed depth travel lets an upward scroll pull the field back in.
      const travel = clamp(1 + scrollVelocity / 260, -24, 25);
      const warp = Math.min(1, Math.abs(scrollVelocity) / 2200);
      const maxTrail = width < 700 ? 48 : 105;
      for (const star of stars) {
        if (delta) star.z -= star.speed * travel * delta;
        const perspective = FOCAL_LENGTH / star.z;
        const depth = Math.min(1, perspective / 2.6);
        const x = centerX + star.x * perspective + pointer.x * depth;
        const y = centerY + star.y * perspective + pointer.y * depth - scroll * 0.012 * depth;
        if (star.z < NEAR_DEPTH || star.z > FAR_DEPTH + 24 || x < -24 || x > width + 24 || y < -24 || y > height + 24) {
          resetStar(star, false, travel < 0);
          continue;
        }
        const radius = Math.min(2.1, star.radius * (0.5 + perspective * 0.6));
        const twinkle = 0.8 + 0.2 * Math.sin(elapsed * 0.7 + star.phase);
        const edgeFade = Math.max(0, Math.min(1, x / 24, (width - x) / 24, y / 24, (height - y) / 24));
        const nearFade = Math.min(1, (star.z - NEAR_DEPTH) / 110);
        const alpha = star.alpha * twinkle * edgeFade * nearFade;

        if (warp > 0.035) {
          // Project the earlier position to form a radial trail. Bounding its
          // length keeps navigation jumps from washing out the page.
          const tailDepth = Math.max(NEAR_DEPTH, star.z + star.speed * travel * 0.2);
          const tailPerspective = FOCAL_LENGTH / tailDepth;
          let dx = star.x * (perspective - tailPerspective);
          let dy = star.y * (perspective - tailPerspective);
          const length = Math.hypot(dx, dy);
          const limit = length ? Math.min(1, maxTrail / length) * warp : 0;
          dx *= limit;
          dy *= limit;
          if (Math.abs(dx) + Math.abs(dy) > 0.5) {
            ctx.strokeStyle = `rgba(225,225,231,${alpha * (0.24 + warp * 0.43)})`;
            ctx.lineWidth = Math.max(0.45, radius * 0.65);
            ctx.beginPath();
            ctx.moveTo(x - dx, y - dy);
            ctx.lineTo(x, y);
            ctx.stroke();
          }
        }
        ctx.fillStyle = `rgba(231,231,234,${alpha})`;
        if (star.square && radius > 0.8) {
          ctx.fillRect(x - radius, y - radius, radius * 1.6, radius * 1.6);
        } else {
          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fill();
        }
        if (radius > 1.2 && warp < 0.35) {
          ctx.strokeStyle = `rgba(238,238,240,${alpha * 0.2})`;
          ctx.lineWidth = 0.5;
          ctx.beginPath();
          ctx.moveTo(x - radius * 2.7, y);
          ctx.lineTo(x + radius * 2.7, y);
          ctx.moveTo(x, y - radius * 2.7);
          ctx.lineTo(x, y + radius * 2.7);
          ctx.stroke();
        }
      }
      canvas.dataset.portalInfluence = portalInfluence.toFixed(3);
      canvas.dataset.warpSpeed = (1 + Math.min(24, Math.abs(scrollVelocity) / 260)).toFixed(2);
      canvas.dataset.scrollVelocity = Math.round(scrollVelocity).toString();
    };

    const animate = (now) => {
      if (disposed || document.hidden || motionRef.current) return;
      if (previousTime !== null && now - previousTime < 1000 / 30) {
        frame = requestAnimationFrame(animate);
        return;
      }
      const delta = previousTime === null ? 0 : Math.min((now - previousTime) / 1000, 0.08);
      previousTime = now;
      elapsed += delta;
      const smoothing = 1 - Math.exp(-delta * 3);
      pointer.x += (targetPointer.x - pointer.x) * smoothing;
      pointer.y += (targetPointer.y - pointer.y) * smoothing;
      if (now - previousScrollTime > 90) targetVelocity *= Math.exp(-delta * 6);
      const response = Math.abs(targetVelocity) > Math.abs(scrollVelocity) ? 8 : 4.5;
      scrollVelocity += (targetVelocity - scrollVelocity) * (1 - Math.exp(-delta * response));
      if (Math.abs(scrollVelocity) < 0.05) scrollVelocity = 0;
      render(delta);
      frame = requestAnimationFrame(animate);
    };

    const start = () => {
      cancelAnimationFrame(frame);
      previousTime = null;
      previousScroll = window.scrollY;
      previousScrollTime = performance.now();
      scrollVelocity = 0;
      targetVelocity = 0;
      canvas.dataset.warpSpeed = '1.00';
      canvas.dataset.scrollVelocity = '0';
      canvas.dataset.motion = motionRef.current || document.hidden ? 'paused' : 'active';
      if (!disposed && !document.hidden && !motionRef.current) frame = requestAnimationFrame(animate);
    };
    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineCap = 'round';
      seed = 821;
      const count = width < 700
        ? Math.min(550, Math.max(360, Math.round(width * height / 640)))
        : Math.min(2200, Math.max(900, Math.round(width * height / 680)));
      stars = Array.from({ length: count }, () => resetStar({}, true));
      canvas.dataset.starCount = count.toString();
      render();
      start();
    };
    const move = (event) => {
      if (motionRef.current) return;
      targetPointer.x = (event.clientX / width - 0.5) * 18;
      targetPointer.y = (event.clientY / height - 0.5) * 18;
    };
    const scroll = () => {
      const now = performance.now();
      const nextScroll = window.scrollY;
      const distance = nextScroll - previousScroll;
      if (!motionRef.current && !document.hidden) {
        // A bounded event interval captures the first wheel/touch movement
        // after idling, while clamping anchor and keyboard navigation jumps.
        const interval = clamp(now - previousScrollTime, 16, 80);
        targetVelocity = clamp(distance * 1000 / interval, -MAX_SCROLL_SPEED, MAX_SCROLL_SPEED);
      }
      previousScroll = nextScroll;
      previousScrollTime = now;
    };

    resumeRef.current = start;
    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', move, { passive: true });
    window.addEventListener('scroll', scroll, { passive: true });
    document.addEventListener('visibilitychange', start);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      resumeRef.current = null;
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('scroll', scroll);
      document.removeEventListener('visibilitychange', start);
    };
  }, []);

  useEffect(() => { resumeRef.current?.(); }, [reducedMotion]);
  return <canvas className="starfield" ref={canvasRef} aria-hidden="true" />;
}
