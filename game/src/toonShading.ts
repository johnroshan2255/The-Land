// Stylised shading after Bruno Simon's folio-2025 (MeshDefaultMaterial, MIT licence, github.com/brunosimon/folio-2025):
// instead of a physical light falloff every surface is its own colour times the sun ("lit") and blends toward its colour
// times a tinted SHADOW colour ("shade") as it turns away from the sun. Shade is never grey, so the world stays rich and
// saturated - the warm-lit / violet-shaded look of his portfolio and of our reference images.
//
// It replaces the Lambert lighting of every MeshLambertMaterial (terrain, props, car, water, smoke) and reuses the
// scene's two lights as its inputs, so no extra uniforms or passes: the directional light's colour x intensity is the
// lit tint and the hemisphere light's sky colour x intensity is the shadow tint (DayNight sets both; intensities are
// scaled by PI there because three's Lambert BRDF divides by PI). Cast shadows (the baked prop-shadow texture on the
// terrain) feed in through `toonDrop` (0 = sunlit .. 1 = in shadow).
import * as THREE from 'three';

const EDGE_LIT = '1.0', EDGE_SHADE = '-0.25';   // Bruno's coreShadowEdgeHigh / Low

const lambert = THREE.ShaderLib.lambert;
lambert.fragmentShader = lambert.fragmentShader
  .replace('#include <aomap_fragment>', 'float toonDrop = 0.0;\n#include <aomap_fragment>')
  .replace(
    'vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;',
    /* glsl */ `
    vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
    #if NUM_DIR_LIGHTS > 0 && NUM_HEMI_LIGHTS > 0
    {
      vec3 base = diffuseColor.rgb;
      vec3 litTint = directionalLights[0].color * RECIPROCAL_PI;
      vec3 shadeTint = hemisphereLights[0].skyColor * RECIPROCAL_PI;
      float ndl = dot(normal, directionalLights[0].direction);
      float core = smoothstep(${EDGE_LIT}, ${EDGE_SHADE}, ndl);
      #ifdef TOON_SHADE_SCALE
      core *= TOON_SHADE_SCALE;
      #endif
      float mixShade = clamp(max(core, toonDrop), 0.0, 1.0);
      outgoingLight = mix(base * litTint, base * shadeTint, mixShade) + totalEmissiveRadiance;
    }
    #endif`,
  );
