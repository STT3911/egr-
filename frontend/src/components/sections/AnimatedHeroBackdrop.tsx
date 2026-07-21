export const AnimatedHeroBackdrop = () => {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute inset-0 registry-grid opacity-45" />
      <div className="absolute inset-0 registry-vignette" />
      <div className="hero-backdrop-orb hero-backdrop-orb-primary" />
      <div className="hero-backdrop-orb hero-backdrop-orb-accent" />
      <div className="hero-backdrop-beam hidden md:block" />
    </div>
  );
};
