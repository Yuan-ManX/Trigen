import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, Icosahedron } from "@react-three/drei";
import * as THREE from "three";

function GenesisCore() {
  const groupRef = useRef<THREE.Group>(null);
  const innerRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (groupRef.current) {
      groupRef.current.rotation.y = t * 0.15;
      groupRef.current.rotation.x = Math.sin(t * 0.2) * 0.1;
    }
    if (innerRef.current) {
      innerRef.current.rotation.y = -t * 0.4;
      innerRef.current.rotation.z = t * 0.2;
    }
  });

  return (
    <group ref={groupRef}>
      <Float speed={1.4} rotationIntensity={0.2} floatIntensity={0.6}>
        <Icosahedron args={[1.6, 1]}>
          <meshBasicMaterial color="#00F0FF" wireframe transparent opacity={0.55} />
        </Icosahedron>
      </Float>

      <mesh ref={innerRef}>
        <icosahedronGeometry args={[0.9, 0]} />
        <meshBasicMaterial color="#FFFFFF" wireframe transparent opacity={0.9} />
      </mesh>

      <mesh scale={1.15}>
        <icosahedronGeometry args={[1.6, 0]} />
        <meshBasicMaterial color="#FFB800" wireframe transparent opacity={0.18} />
      </mesh>

      <points>
        <icosahedronGeometry args={[2.4, 2]} />
        <pointsMaterial size={0.025} color="#00F0FF" transparent opacity={0.6} sizeAttenuation />
      </points>
    </group>
  );
}

function OrbitRing({
  radius,
  tilt,
  color,
  speed,
}: {
  radius: number;
  tilt: number;
  color: string;
  speed: number;
}) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.z = state.clock.getElapsedTime() * speed;
    }
  });
  return (
    <mesh ref={ref} rotation={[tilt, 0, 0]}>
      <torusGeometry args={[radius, 0.004, 16, 128]} />
      <meshBasicMaterial color={color} transparent opacity={0.4} />
    </mesh>
  );
}

function ParticleCloud({ count = 1800 }: { count?: number }) {
  const ref = useRef<THREE.Points>(null);

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 4 + Math.random() * 6;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      arr[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      arr[i * 3 + 2] = r * Math.cos(phi);
    }
    geo.setAttribute("position", new THREE.BufferAttribute(arr, 3));
    return geo;
  }, [count]);

  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.y = state.clock.getElapsedTime() * 0.03;
      ref.current.rotation.x = Math.sin(state.clock.getElapsedTime() * 0.05) * 0.05;
    }
  });

  return (
    <points ref={ref} geometry={geometry}>
      <pointsMaterial
        size={0.018}
        color="#FFFFFF"
        transparent
        opacity={0.7}
        sizeAttenuation
      />
    </points>
  );
}

function MouseRig({ children }: { children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null);
  const { pointer } = useThree();

  useFrame(() => {
    if (group.current) {
      group.current.rotation.y = THREE.MathUtils.lerp(
        group.current.rotation.y,
        pointer.x * 0.4,
        0.05
      );
      group.current.rotation.x = THREE.MathUtils.lerp(
        group.current.rotation.x,
        -pointer.y * 0.3,
        0.05
      );
    }
  });

  return <group ref={group}>{children}</group>;
}

export default function GenesisScene() {
  return (
    <Canvas
      camera={{ position: [0, 0, 7], fov: 45 }}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true }}
      style={{ background: "transparent" }}
    >
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 5, 5]} intensity={0.8} />

      <MouseRig>
        <GenesisCore />
        <OrbitRing radius={2.6} tilt={1.2} color="#00F0FF" speed={0.3} />
        <OrbitRing radius={3.1} tilt={-0.6} color="#FFB800" speed={-0.2} />
        <OrbitRing radius={3.6} tilt={0.4} color="#FFFFFF" speed={0.15} />
        <ParticleCloud count={1800} />
      </MouseRig>
    </Canvas>
  );
}
