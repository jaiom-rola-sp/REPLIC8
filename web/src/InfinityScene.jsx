import { lazy, Suspense, useEffect, useRef, useState } from 'react';

const ProceduralInfinityScene = lazy(() => import('./ProceduralInfinity.jsx'));
const TAU = Math.PI * 2;
const lerp = (start, end, amount) => start + (end - start) * amount;
const clamp = (value, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const ease = value => value * value * (3 - 2 * value);
const interval = (start, end, value) => clamp((value - start) / Math.max(0.000001, end - start));

function betweenFrames(frames, amount) {
  const nextIndex = frames.findIndex(frame => frame.at >= amount);
  const next = frames[nextIndex < 0 ? frames.length - 1 : nextIndex];
  const previous = frames[Math.max(0, nextIndex - 1)];
  const blend = ease(interval(previous.at, next.at, amount));
  const pose = {};
  for (const key of ['x', 'y', 'height', 'roll', 'pitch', 'turn', 'alpha']) {
    pose[key] = lerp(previous[key] ?? 0, next[key] ?? 0, blend);
  }
  return pose;
}

function storyPose(scroll, sections, viewport, anchor, restrained) {
  const { width, height } = viewport;
  const mobile = width < 700;
  const normalSize = Math.min(height * 0.43, mobile ? 260 : 390);
  const right = mobile ? 0.68 : 0.78;
  const discover = sections.discover?.top ?? height;
  const threshold = sections.threshold ?? { top: discover + height, height: height * 1.8 };
  const connect = sections.connect?.top ?? threshold.top + threshold.height;
  const evolve = sections.evolve?.top ?? connect + height;
  const universe = sections.universe?.top ?? evolve + height;
  const portalStart = threshold.top - height * 0.35;
  const portalProgress = interval(portalStart, portalStart + threshold.height - height * 0.25, scroll);
  const heroRelease = ease(interval(0, discover * 0.72, scroll));
  const frame = (at, x, y, size, roll, alpha = 1, pitch = 0, turn = 0) => ({
    at, x: width * x, y: height * y, height: normalSize * size, roll, alpha, pitch, turn,
  });

  // Motion-off still follows the reading flow, but omits rotations and the
  // tunnel-sized zoom. A small core keeps the relationship between chapters.
  if (restrained) {
    if (scroll < discover) return {
      phase: 'origin', portalProgress,
      x: lerp(anchor.x, width * right, heroRelease),
      y: lerp(anchor.y - scroll, height * 0.57, heroRelease),
      height: lerp(anchor.height, normalSize * 0.76, heroRelease),
      roll: Math.PI / 2 * heroRelease, pitch: 0, turn: 0, alpha: 1, idleWeight: 0,
    };
    if (scroll < portalStart) return { ...frame(0, right, 0.59, 0.76, Math.PI / 2), phase: 'discover', portalProgress, idleWeight: 0 };
    if (scroll < connect) return { ...frame(0, 0.5, 0.62, 0.76, Math.PI / 2, 0.9), phase: 'portal-still', portalProgress, idleWeight: 0 };
    if (scroll < evolve) return { ...frame(0, 0.5, 0.67, 0.76, Math.PI / 2), phase: 'connect', portalProgress, idleWeight: 0 };
    if (scroll < universe) return { ...frame(0, right, 0.58, 0.76, Math.PI / 2), phase: 'evolve', portalProgress, idleWeight: 0 };
    const exit = ease(interval(universe, universe + height * 0.75, scroll));
    return { ...frame(0, 0.5, 0.46, lerp(0.6, 0.12, exit), Math.PI / 2, 1 - exit), phase: 'universe', portalProgress, idleWeight: 0 };
  }

  if (scroll < discover) {
    const travel = interval(0, discover, scroll);
    const pose = betweenFrames([
      { at: 0, x: anchor.x, y: anchor.y - scroll, height: anchor.height, roll: 0, alpha: 1 },
      frame(0.2, mobile ? 0.72 : 0.82, 0.43, 0.86, Math.PI * 0.22, 1, 0.06, -0.08),
      frame(0.55, mobile ? 0.63 : 0.7, 0.48, 1.2, Math.PI * 1.6, 1, -0.18, 0.22),
      frame(1, right, 0.55, 1, Math.PI * 2.5, 1, 0.12, -0.12),
    ], travel);
    return { ...pose, phase: 'origin', portalProgress, idleWeight: 1 + heroRelease * 0.25 };
  }

  if (scroll < portalStart) {
    const travel = interval(discover, portalStart, scroll);
    const pose = betweenFrames([
      frame(0, right, 0.55, 1, Math.PI * 2.5, 1, 0.12, -0.12),
      frame(0.44, mobile ? 0.64 : 0.77, 0.47, 1.25, Math.PI * 3.25, 1, -0.2, 0.3),
      frame(0.76, mobile ? 0.62 : 0.67, 0.57, 1.1, Math.PI * 4.15, 1, 0.15, -0.2),
      frame(1, 0.5, 0.55, 1.2, Math.PI * 4.5, 1, 0.1, 0.1),
    ], travel);
    return { ...pose, phase: 'discover', portalProgress, idleWeight: 1.15 };
  }

  if (scroll < connect) {
    const p = portalProgress;
    const alignment = ease(interval(0.28, 0.46, p));
    const flight = ease(interval(0.43, 0.97, p));
    const initialHeight = normalSize * 1.2;
    const portalHeight = Math.min(width * 0.83, height * 0.75, 650);
    const maximumHeight = Math.min(Math.max(width, height) * 6.3, 11000);
    const entryHeight = lerp(initialHeight, portalHeight, ease(interval(0, 0.36, p)));
    const sculptureHeight = entryHeight * Math.exp(Math.log(maximumHeight / portalHeight) * flight);
    const roll = lerp(Math.PI * 4.5, Math.PI * 6.5, ease(interval(0, 0.36, p)));

    // The upper opening in the Higgsfield square is approximately (0.5,
    // 0.28). Rotate this local offset with the artwork, then keep that hole
    // on the camera center. Zooming around the image center would hit the
    // crossing instead of passing through an opening.
    const loopOffset = -0.22 * sculptureHeight;
    const loopX = -Math.sin(roll) * loopOffset;
    const loopY = Math.cos(roll) * loopOffset;
    const x = width * 0.5 - loopX * alignment;
    // Give the incoming chapter title room before aligning the camera.
    const entryY = lerp(height * 0.55, height * 0.74, ease(interval(0, 0.1, p)));
    const y = lerp(entryY, height * 0.5, alignment) - loopY * alignment;
    return {
      phase: p < 0.43 ? 'portal-align' : p < 0.86 ? 'portal-flight' : 'portal-exit',
      portalProgress, x, y, height: sculptureHeight, roll,
      pitch: (1 - alignment) * 0.1,
      turn: (1 - alignment) * 0.1,
      alpha: 1 - ease(interval(0.86, 1, p)),
      idleWeight: 1 - alignment,
    };
  }

  if (scroll < evolve) {
    const travel = interval(connect, evolve, scroll);
    const pose = betweenFrames([
      frame(0, 0.5, 0.67, 0.36, Math.PI * 6.5, 0),
      frame(0.2, 0.5, 0.67, 1.12, Math.PI * 6.58, 1, 0.06, 0.1),
      frame(0.55, 0.5, 0.64, 0.94, Math.PI * 7.2, 1, -0.12, -0.2),
      frame(1, right, 0.55, 1, Math.PI * 8.5, 1, 0.15, 0.12),
    ], travel);
    return { ...pose, phase: 'connect', portalProgress, idleWeight: 1.2 };
  }

  if (scroll < universe) {
    const travel = interval(evolve, universe, scroll);
    const pose = betweenFrames([
      frame(0, right, 0.55, 1, Math.PI * 8.5, 1, 0.15, 0.12),
      frame(0.35, mobile ? 0.64 : 0.83, 0.46, 1.3, Math.PI * 9.2, 1, -0.18, -0.3),
      frame(0.7, mobile ? 0.62 : 0.74, 0.57, 0.85, Math.PI * 10, 1, 0.2, 0.2),
      frame(1, mobile ? 0.58 : 0.7, 0.5, 0.75, Math.PI * 10.5, 1, 0.06, 0.1),
    ], travel);
    return { ...pose, phase: 'evolve', portalProgress, idleWeight: 1.1 };
  }

  const travel = ease(interval(universe, universe + height * 0.9, scroll));
  return {
    phase: 'universe', portalProgress,
    x: lerp(width * (mobile ? 0.58 : 0.7), width * 0.5, travel),
    y: lerp(height * 0.5, height * 0.38, travel),
    height: lerp(normalSize * 0.75, normalSize * 0.1, travel),
    roll: Math.PI * (10.5 + travel), pitch: 0.06, turn: 0.1,
    alpha: 1 - travel, idleWeight: 1 - travel,
  };
}

function GeneratedInfinityScene({ progress, reducedMotion, className, onError }) {
  const imageRef = useRef(null);
  const sceneRef = useRef(null);
  const reducedMotionRef = useRef(reducedMotion);
  const drawRef = useRef(null);
  const startRef = useRef(null);
  const animationFrameRef = useRef(0);
  reducedMotionRef.current = reducedMotion;

  useEffect(() => {
    const image = imageRef.current;
    const scene = sceneRef.current;
    if (!image || !scene) return undefined;

    let disposed = false;
    let viewport = { width: window.innerWidth, height: window.innerHeight };
    let anchor = { x: viewport.width * 0.735, y: viewport.height * 0.405, height: 200 };
    let sections = {};
    let resizeObserver;
    let activeElapsed = 0;
    let previousFrame = null;

    const draw = () => {
      if (disposed) return;
      const pose = storyPose(window.scrollY, sections, viewport, anchor, reducedMotionRef.current);
      const cycle = seconds => Math.sin(activeElapsed * TAU / seconds);
      const idle = pose.idleWeight;
      const float = cycle(10) * 6 * idle;
      const pitch = pose.pitch + cycle(14) * 0.07 * idle;
      const turn = pose.turn + cycle(16) * 0.14 * idle;
      const lean = pose.roll + cycle(12) * Math.PI / 36 * idle;
      const scale = pose.height / 350;
      image.style.transform = `translate3d(${pose.x}px, ${pose.y + float}px, 0) translate(-50%, -50%) perspective(1000px) rotateX(${pitch}rad) rotateY(${turn}rad) rotateZ(${lean}rad) scale(${scale})`;
      image.style.opacity = String(pose.alpha);
      scene.style.zIndex = pose.phase.startsWith('portal') && !reducedMotionRef.current ? '3' : '1';
      scene.dataset.phase = pose.phase;
      scene.dataset.portalProgress = pose.portalProgress.toFixed(3);
      scene.dataset.sculptureScale = scale.toFixed(3);
    };

    const animate = now => {
      if (disposed || document.hidden || reducedMotionRef.current) {
        previousFrame = null;
        return;
      }
      if (previousFrame !== null) activeElapsed += Math.min(now - previousFrame, 100) / 1000;
      previousFrame = now;
      draw();
      animationFrameRef.current = requestAnimationFrame(animate);
    };
    const start = () => {
      cancelAnimationFrame(animationFrameRef.current);
      previousFrame = null;
      if (disposed || document.hidden) return;
      draw();
      if (!reducedMotionRef.current) animationFrameRef.current = requestAnimationFrame(animate);
    };
    const measure = () => {
      if (disposed) return;
      viewport = { width: document.documentElement.clientWidth, height: window.innerHeight };
      const marker = document.querySelector('.hero-eight');
      if (marker) {
        const rect = marker.getBoundingClientRect();
        if (rect.width && rect.height) anchor = {
          x: rect.left + rect.width / 2,
          y: rect.top + window.scrollY + rect.height * 0.52,
          height: rect.height * 0.95,
        };
      }
      sections = {};
      for (const id of ['origin', 'discover', 'threshold', 'connect', 'evolve', 'universe']) {
        const element = document.getElementById(id);
        if (!element) continue;
        const rect = element.getBoundingClientRect();
        sections[id] = { top: rect.top + window.scrollY, height: rect.height };
      }
      draw();
    };

    drawRef.current = draw;
    startRef.current = start;
    measure();
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(measure);
      resizeObserver.observe(document.body);
      const marker = document.querySelector('.hero-eight');
      if (marker) resizeObserver.observe(marker);
    }
    window.addEventListener('resize', measure, { passive: true });
    document.addEventListener('visibilitychange', start);
    document.fonts?.ready.then(measure);
    document.fonts?.addEventListener?.('loadingdone', measure);
    start();

    return () => {
      disposed = true;
      cancelAnimationFrame(animationFrameRef.current);
      resizeObserver?.disconnect();
      window.removeEventListener('resize', measure);
      document.removeEventListener('visibilitychange', start);
      document.fonts?.removeEventListener?.('loadingdone', measure);
      drawRef.current = null;
      startRef.current = null;
    };
  }, []);

  useEffect(() => { drawRef.current?.(); }, [progress]);
  useEffect(() => { startRef.current?.(); }, [reducedMotion]);

  return <div
    ref={sceneRef}
    className={`infinity-scene infinity-scene-artwork ${className}`.trim()}
    aria-hidden="true"
    style={{ position: 'fixed', inset: 0, zIndex: 1, pointerEvents: 'none', overflow: 'hidden' }}
  >
    <img
      ref={imageRef}
      src="/assets/silver-eight.png"
      alt=""
      width="350"
      height="350"
      fetchPriority="high"
      decoding="async"
      draggable={false}
      onLoad={() => drawRef.current?.()}
      onError={onError}
      style={{
        position: 'absolute', left: 0, top: 0, width: 350, height: 350,
        maxWidth: 'none', objectFit: 'contain', mixBlendMode: 'screen',
        transformOrigin: '50% 50%', willChange: 'transform, opacity',
        opacity: 0, userSelect: 'none',
      }}
    />
  </div>;
}

export default function InfinityScene({ progress = 0, reducedMotion = false, className = '' }) {
  const [assetFailed, setAssetFailed] = useState(false);
  return assetFailed ? (
    <Suspense fallback={null}><ProceduralInfinityScene progress={progress} reducedMotion={reducedMotion} className={className} /></Suspense>
  ) : (
    <GeneratedInfinityScene progress={progress} reducedMotion={reducedMotion} className={className} onError={() => setAssetFailed(true)} />
  );
}
