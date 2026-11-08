import { useEffect, useId, useRef, useState } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RectAreaLightUniformsLib } from 'three/addons/lights/RectAreaLightUniformsLib.js';

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const ease = (value) => value * value * (3 - 2 * value);

// Positions are viewport fractions; sizes are relative to the hero sculpture.
const poses = [
  { at: 0, x: 0.735, y: 0.405, size: 1, rz: 0, rx: 0.02, ry: -0.04, alpha: 1 },
  { at: 0.06, x: 0.79, y: 0.43, size: 0.85, rz: -0.12, rx: 0.08, ry: 0.1, alpha: 1 },
  { at: 0.12, x: 0.77, y: 0.49, size: 1, rz: -0.65, rx: 0.1, ry: 0.12, alpha: 1 },
  { at: 0.18, x: 0.77, y: 0.55, size: 1, rz: -Math.PI / 2 + 0.1, rx: 0.08, ry: -0.1, alpha: 1 },
  { at: 0.36, x: 0.77, y: 0.55, size: 0.96, rz: -Math.PI / 2 - 0.07, rx: 0.16, ry: 0.12, alpha: 1 },
  { at: 0.43, x: 0.5, y: 0.65, size: 1.04, rz: -Math.PI / 2, rx: 0.08, ry: 0.1, alpha: 1 },
  { at: 0.6, x: 0.5, y: 0.65, size: 1.04, rz: -Math.PI / 2 + 0.06, rx: -0.08, ry: -0.1, alpha: 1 },
  { at: 0.67, x: 0.77, y: 0.55, size: 0.96, rz: -Math.PI / 2 + 0.18, rx: 0.1, ry: 0.12, alpha: 1 },
  { at: 0.8, x: 0.77, y: 0.55, size: 0.9, rz: -Math.PI / 2 - 0.12, rx: 0.12, ry: -0.1, alpha: 1 },
  { at: 0.87, x: 0.5, y: 0.45, size: 0.53, rz: -Math.PI / 2, rx: 0.08, ry: 0.08, alpha: 0.7 },
  { at: 0.95, x: 0.5, y: 0.43, size: 0.2, rz: -Math.PI / 2 - 0.1, rx: 0.04, ry: 0.04, alpha: 0.3 },
  { at: 1, x: 0.5, y: 0.42, size: 0.1, rz: -Math.PI / 2 - 0.14, rx: 0.02, ry: 0.02, alpha: 0 },
];

function poseAt(progress, mobile = false) {
  const p = clamp(Number.isFinite(progress) ? progress : 0, 0, 1);
  const rightIndex = poses.findIndex((pose) => pose.at >= p);
  const right = poses[rightIndex < 0 ? poses.length - 1 : rightIndex];
  const left = poses[Math.max(0, rightIndex - 1)];
  const amount = ease(right.at === left.at ? 0 : (p - left.at) / (right.at - left.at));
  const pose = {};
  for (const key of ['x', 'y', 'size', 'rz', 'rx', 'ry', 'alpha']) {
    pose[key] = THREE.MathUtils.lerp(left[key], right[key], amount);
  }

  if (mobile) {
    pose.size *= 0.62;
    pose.x = clamp(pose.x, 0.3, 0.67);
    const lowerWeight = ease(clamp(p / 0.18, 0, 1))
      * (1 - ease(clamp((p - 0.82) / 0.08, 0, 1)));
    pose.y = THREE.MathUtils.lerp(pose.y, Math.max(pose.y, 0.64), lowerWeight);
  }

  return pose;
}

class InfinityCurve extends THREE.Curve {
  getPoint(t, target = new THREE.Vector3()) {
    const angle = t * Math.PI * 2;
    const sine = Math.sin(angle);
    const cosine = Math.cos(angle);
    const denominator = 1 + sine * sine;

    // The two center crossings sit at different depths, forming one continuous
    // closed tube rather than two intersecting toruses.
    return target.set(
      (2.4 * sine * cosine) / denominator,
      (1.62 * cosine) / denominator,
      0.34 * sine,
    );
  }
}

function addReflectionPanel(environment, width, height, position, intensity) {
  const panel = new THREE.Mesh(
    new THREE.PlaneGeometry(width, height),
    new THREE.MeshBasicMaterial({
      color: new THREE.Color().setScalar(intensity),
      side: THREE.DoubleSide,
      toneMapped: false,
    }),
  );
  panel.position.set(...position);
  panel.lookAt(0, 0, 0);
  environment.add(panel);
}

function disposeScene(scene) {
  const geometries = new Set();
  const materials = new Set();
  scene.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    const list = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of list) if (material) materials.add(material);
  });
  geometries.forEach((geometry) => geometry.dispose());
  materials.forEach((material) => material.dispose());
}

function SilverFallback({ progress, id }) {
  const [viewport, setViewport] = useState(() => ({
    width: typeof window === 'undefined' ? 1500 : window.innerWidth,
    height: typeof window === 'undefined' ? 900 : window.innerHeight,
  }));

  useEffect(() => {
    const resize = () => setViewport({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener('resize', resize, { passive: true });
    return () => window.removeEventListener('resize', resize);
  }, []);

  const mobile = viewport.width < 700;
  const pose = poseAt(progress, mobile);
  const height = clamp(viewport.height * 0.43, 240, 350) * pose.size;
  const path = 'M120 190 C35 133 34 42 120 42 C206 42 205 133 120 190 C35 247 34 338 120 338 C206 338 205 247 120 190';

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 240 380"
      style={{
        position: 'absolute',
        left: `${pose.x * 100}%`,
        top: `${pose.y * 100}%`,
        height,
        width: height * (240 / 380),
        opacity: pose.alpha,
        overflow: 'visible',
        transform: `translate(-50%, -50%) rotate(${-pose.rz}rad)`,
      }}
    >
      <defs>
        <linearGradient id={`${id}-silver`} x1="0" y1="0" x2="1" y2="0.8">
          <stop offset="0" stopColor="#f9fafb" />
          <stop offset="0.18" stopColor="#c9cace" />
          <stop offset="0.34" stopColor="#45474b" />
          <stop offset="0.47" stopColor="#ffffff" />
          <stop offset="0.6" stopColor="#d0d1d3" />
          <stop offset="0.74" stopColor="#595b61" />
          <stop offset="0.87" stopColor="#fafafa" />
          <stop offset="1" stopColor="#9fa2a6" />
        </linearGradient>
      </defs>
      <path d={path} fill="none" stroke="#8e9196" strokeWidth="48" strokeLinecap="round" />
      <path d={path} fill="none" stroke={`url(#${id}-silver)`} strokeWidth="44" strokeLinecap="round" />
      <path
        d="M72 152 C85 166 102 178 120 190 C138 202 154 217 165 232"
        fill="none"
        stroke={`url(#${id}-silver)`}
        strokeWidth="44"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function ProceduralInfinityScene({ progress = 0, reducedMotion = false, className = '' }) {
  const containerRef = useRef(null);
  const progressRef = useRef(progress);
  const reducedMotionRef = useRef(reducedMotion);
  const [fallback, setFallback] = useState(false);
  const fallbackId = useId().replaceAll(':', '');
  const drawRef = useRef(null);
  const startRef = useRef(null);

  progressRef.current = progress;
  reducedMotionRef.current = reducedMotion;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    let renderer;
    let scene;
    let environment;
    let pmrem;
    let environmentMap;
    let animationFrame = 0;
    let disposed = false;
    let contextLost = false;
    let resizeObserver;
    let width = 1;
    let height = 1;
    let worldHeight = 1;
    let worldWidth = 1;
    let sculptureHeight = 350;
    let activeElapsed = 0;
    let previousFrame = null;

    const onContextLost = (event) => {
      event.preventDefault();
      contextLost = true;
      cancelAnimationFrame(animationFrame);
      if (!disposed) setFallback(true);
    };

    let onResize;
    let onVisibility;

    try {
      renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: 'high-performance',
        failIfMajorPerformanceCaveat: false,
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.setClearColor(0x000000, 0);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.2;
      renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;';
      renderer.domElement.setAttribute('aria-hidden', 'true');
      renderer.domElement.addEventListener('webglcontextlost', onContextLost, false);
      container.appendChild(renderer.domElement);

      scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 80);
      camera.position.set(0, 0, 12);

      RectAreaLightUniformsLib.init();
      pmrem = new THREE.PMREMGenerator(renderer);
      environment = new RoomEnvironment();
      addReflectionPanel(environment, 2, 7, [-4, 1, 4], 6);
      addReflectionPanel(environment, 1.3, 6, [4, 2, 2], 4);
      addReflectionPanel(environment, 5, 1.2, [0, 5, 2], 5);
      addReflectionPanel(environment, 2.5, 2, [1, -3, 4], 2);
      environmentMap = pmrem.fromScene(environment, 0.025);
      scene.environment = environmentMap.texture;
      disposeScene(environment);
      environment = undefined;
      pmrem.dispose();
      pmrem = undefined;

      const sculpture = new THREE.Group();
      const geometry = new THREE.TubeGeometry(new InfinityCurve(), 320, 0.24, 40, true);
      const material = new THREE.MeshStandardMaterial({
        color: 0xe7e7e7,
        metalness: 1,
        roughness: 0.19,
        envMapIntensity: 1.6,
        transparent: true,
      });
      sculpture.add(new THREE.Mesh(geometry, material));
      scene.add(sculpture);

      const keyLight = new THREE.RectAreaLight(0xffffff, 7, 4, 6);
      keyLight.position.set(-4, 4, 5);
      keyLight.lookAt(0, 0, 0);
      scene.add(keyLight);

      const edgeLight = new THREE.RectAreaLight(0xffffff, 5, 2, 7);
      edgeLight.position.set(5, 1, 3);
      edgeLight.lookAt(0, 0, 0);
      scene.add(edgeLight);

      const topLight = new THREE.DirectionalLight(0xffffff, 2.5);
      topLight.position.set(0, 6, 4);
      scene.add(topLight);

      const fillLight = new THREE.DirectionalLight(0xffffff, 1.1);
      fillLight.position.set(-3, -3, 3);
      scene.add(fillLight);

      const draw = () => {
        if (disposed || contextLost) return;
        const pose = poseAt(progressRef.current, width < 700);
        const release = ease(clamp(progressRef.current / 0.1, 0, 1));
        const idle = THREE.MathUtils.lerp(1, 1.25, release);
        const cycle = (seconds) => Math.sin(activeElapsed * Math.PI * 2 / seconds);
        const float = cycle(10) * 6 * idle * worldHeight / height;
        const scale = (sculptureHeight * pose.size * worldHeight) / (height * 3.72);

        sculpture.position.set((pose.x - 0.5) * worldWidth, (0.5 - pose.y) * worldHeight + float, 0);
        sculpture.scale.setScalar(scale);
        material.opacity = pose.alpha;
        sculpture.rotation.set(
          pose.rx + cycle(14) * 0.07 * idle,
          pose.ry + cycle(16) * 0.14 * idle,
          pose.rz + cycle(12) * (Math.PI / 36) * idle,
        );
        renderer.render(scene, camera);
      };

      const animate = (now) => {
        if (disposed || contextLost || document.hidden || reducedMotionRef.current) {
          previousFrame = null;
          return;
        }
        if (previousFrame !== null) activeElapsed += Math.min(now - previousFrame, 100) / 1000;
        previousFrame = now;
        draw();
        animationFrame = requestAnimationFrame(animate);
      };

      onResize = () => {
        width = Math.max(1, container.clientWidth);
        height = Math.max(1, container.clientHeight);
        sculptureHeight = clamp(height * 0.43, 240, 350);
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        worldHeight = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.position.z;
        worldWidth = worldHeight * camera.aspect;
        draw(performance.now());
      };

      onVisibility = () => {
        cancelAnimationFrame(animationFrame);
        previousFrame = null;
        if (document.hidden || disposed || contextLost) return;
        draw();
        if (!reducedMotionRef.current) animationFrame = requestAnimationFrame(animate);
      };
      drawRef.current = draw;
      startRef.current = onVisibility;

      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(onResize);
        resizeObserver.observe(container);
      }
      window.addEventListener('resize', onResize, { passive: true });
      document.addEventListener('visibilitychange', onVisibility);
      onResize();
      onVisibility();
      setFallback(false);
    } catch {
      drawRef.current = null;
      startRef.current = null;
      setFallback(true);
      cancelAnimationFrame(animationFrame);
      resizeObserver?.disconnect();
      if (onResize) window.removeEventListener('resize', onResize);
      if (onVisibility) document.removeEventListener('visibilitychange', onVisibility);
      if (scene) disposeScene(scene);
      if (environment) disposeScene(environment);
      environmentMap?.dispose();
      pmrem?.dispose();
      if (renderer) {
        renderer.domElement.removeEventListener('webglcontextlost', onContextLost);
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      }
      scene = undefined;
      environment = undefined;
      environmentMap = undefined;
      pmrem = undefined;
      renderer = undefined;
    }

    return () => {
      disposed = true;
      drawRef.current = null;
      startRef.current = null;
      cancelAnimationFrame(animationFrame);
      resizeObserver?.disconnect();
      if (onResize) window.removeEventListener('resize', onResize);
      if (onVisibility) document.removeEventListener('visibilitychange', onVisibility);
      if (scene) disposeScene(scene);
      if (environment) disposeScene(environment);
      environmentMap?.dispose();
      pmrem?.dispose();
      if (renderer) {
        renderer.domElement.removeEventListener('webglcontextlost', onContextLost);
        renderer.dispose();
        renderer.forceContextLoss();
        renderer.domElement.remove();
      }
    };
  }, []);

  useEffect(() => { drawRef.current?.(); }, [progress]);
  useEffect(() => { startRef.current?.(); }, [reducedMotion]);

  return (
    <div
      ref={containerRef}
      className={`infinity-scene ${className}`.trim()}
      aria-hidden="true"
      style={{ position: 'fixed', inset: 0, zIndex: 1, pointerEvents: 'none', overflow: 'hidden' }}
    >
      {fallback && <SilverFallback progress={progress} id={fallbackId} />}
    </div>
  );
}

