import { useEffect, useRef } from "react";

const vertex = `
attribute vec2 point;
varying vec2 uv;
void main() { uv = point * .5 + .5; gl_Position = vec4(point, 0., 1.); }
`;

const fragment = `
precision mediump float;
varying vec2 uv;
uniform sampler2D earth;
uniform vec2 size;
uniform float angle;
void main() {
  vec2 p = (uv - vec2(.5)) * size / min(size.x, size.y) / .38;
  float r = length(p);
  vec3 mint = vec3(.26,.86,.61);
  if (r >= 1.) {
    gl_FragColor = vec4(0.);
    return;
  }
  vec3 n = vec3(p, sqrt(max(0., 1.-dot(p,p))));
  vec3 axis = vec3(n.x, n.y * .96 + n.z * .28, n.z * .96 - n.y * .28);
  vec2 map = vec2(fract(atan(axis.x, axis.z)/6.2831853 + angle),
    acos(clamp(axis.y,-1.,1.))/3.14159265);
  vec3 color = texture2D(earth, map).rgb;
  float light = smoothstep(-.38,.74,dot(n,normalize(vec3(-.53,.48,.70))));
  vec3 lit = mix(vec3(.015,.035,.078), color * vec3(.47,.77,.91), light);
  lit += mint * pow(1.-n.z, 4.) * (.21 + .53*light);
  float coverage = 1. - smoothstep(.997, 1., r);
  gl_FragColor = vec4(lit * coverage, coverage);
}
`;

export function AscendEarth() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true });
    if (!gl) return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const program = gl.createProgram();
    const buffer = gl.createBuffer();
    const texture = gl.createTexture();
    const shaders: WebGLShader[] = [];
    const dispose = () => {
      shaders.forEach((shader) => gl.deleteShader(shader));
      gl.deleteProgram(program);
      gl.deleteBuffer(buffer);
      gl.deleteTexture(texture);
    };
    function compile(type: number, source: string) {
      const shader = gl!.createShader(type);
      if (!shader) return false;
      shaders.push(shader);
      gl!.shaderSource(shader, source);
      gl!.compileShader(shader);
      if (!gl!.getShaderParameter(shader, gl!.COMPILE_STATUS)) return false;
      gl!.attachShader(program!, shader);
      return true;
    }
    if (!program || !buffer || !texture || !compile(gl.VERTEX_SHADER, vertex) ||
        !compile(gl.FRAGMENT_SHADER, fragment)) {
      dispose();
      return;
    }
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      dispose();
      return;
    }
    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    const point = gl.getAttribLocation(program, "point");
    gl.enableVertexAttribArray(point);
    gl.vertexAttribPointer(point, 2, gl.FLOAT, false, 0, 0);
    const size = gl.getUniformLocation(program, "size");
    const angle = gl.getUniformLocation(program, "angle");
    const image = new Image();
    let frame = 0;
    let ready = false;
    let visible = true;
    const start = performance.now();
    function draw(now: number) {
      if (!ready || !visible || document.hidden || gl!.isContextLost()) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      const width = Math.max(1, Math.round(canvas!.clientWidth * ratio));
      const height = Math.max(1, Math.round(canvas!.clientHeight * ratio));
      if (width !== canvas!.width || height !== canvas!.height) {
        canvas!.width = width;
        canvas!.height = height;
      }
      gl!.viewport(0, 0, width, height);
      gl!.uniform2f(size, width, height);
      gl!.uniform1f(angle, .56 + (motion.matches ? 0 : (now - start) / 240000 + window.scrollY / 16000));
      gl!.drawArrays(gl!.TRIANGLE_STRIP, 0, 4);
      canvas!.dataset.ready = "true";
      if (!motion.matches) frame = requestAnimationFrame(draw);
    }
    const refresh = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(draw);
    };
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      refresh();
    });
    observer.observe(canvas);
    const lost = () => { delete canvas.dataset.ready; cancelAnimationFrame(frame); };
    canvas.addEventListener("webglcontextlost", lost);
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("resize", refresh);
    motion.addEventListener("change", refresh);
    image.onload = () => {
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
      ready = true;
      refresh();
    };
    image.src = import.meta.env.BASE_URL + "ascend-earth.jpg";
    return () => {
      image.onload = null;
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener("webglcontextlost", lost);
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("resize", refresh);
      motion.removeEventListener("change", refresh);
      delete canvas.dataset.ready;
      dispose();
    };
  }, []);

  return <div className="ascend-earth" aria-hidden="true">
    <div className="ascend-earth-fallback" />
    <canvas ref={ref} />
  </div>;
}
