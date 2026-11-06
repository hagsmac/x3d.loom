// loom:sim
// The Feel Card: every number that decides how Nib moves. Units are metres, seconds, m/s, m/s².
// tests/feel.test.mjs measures the resulting motion (apex height, time to apex, jump distance,
// coyote and buffer windows) and gates it against the windows in FEEL_WINDOWS.

export const HZ = 120;
export const DT = 1 / HZ;

export const FEEL = {
  gravity: 38,          // base gravity on Nib while rising with jump held
  fallMul: 1.7,         // falling: heavier, so jumps land crisply
  cutMul: 2.7,          // rising with jump released: short hops (variable jump height)
  apexV: 2.4,           // |vy| under this counts as the apex ...
  apexMul: 0.55,        // ... where gravity eases off while jump is held (hang time)
  maxFall: 23,

  runMax: 8.6, groundAccel: 78, groundDecel: 100, turnAccel: 150,
  airAccel: 52, airDrag: 6, overspeedDrag: 10,

  jumpV: 15.4,
  coyote: 0.10,         // jump still allowed this long after walking off a ledge
  buffer: 0.13,         // a jump pressed this early before landing still fires

  wallSlide: 3.4, wallJumpVx: 9.6, wallJumpVy: 13.6, wallLock: 0.16, wallProbe: 0.14,

  poundHover: 0.11, poundV: 28, poundRadius: 4.0, poundKick: 10,

  hookRange: 5.4, hookMin: 1.6, hookPump: 17, hookReel: 4.5, hookBoost: 5.0, hookCooldown: 0.22,

  springV: 21.5, superSpringMul: 1.32,

  heroHx: 0.36, heroHy: 0.47, heroMass: 1,
  magnet: 2.0, magnetSpeed: 16, pickR: 0.7,
  respawn: 0.8, hitstop: 0.075,
};

/** Windows the feel test enforces; each is [low, high] for the measured quantity. */
export const FEEL_WINDOWS = {
  apexHeightFull: [3.0, 3.6],      // m, jump held to the apex from flat ground
  apexHeightTap: [0.9, 1.6],       // m, jump released after one frame
  timeToApex: [0.36, 0.5],         // s
  runJumpDistance: [6.0, 8.2],     // m, flat ground to the same height, full speed, jump held
  timeToFullSpeed: [0.08, 0.16],   // s, from standing
  stopDistance: [0.25, 0.6],       // m, from full speed, input released
  coyoteFrames: [10, 14],          // frames after leaving a ledge where jump still fires
  bufferFrames: [12, 17],          // frames before landing where a press still fires
  wallJumpHeight: [2.0, 3.2],      // m gained by one wall jump
};
