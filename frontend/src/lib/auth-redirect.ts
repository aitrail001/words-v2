export const redirectToLogin = (): void => {
  if (typeof window === "undefined") return;
  window.location.assign("/login");
};
