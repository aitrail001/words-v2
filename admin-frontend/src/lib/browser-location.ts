type BrowserLocation = Pick<Location, "assign">;

export const assignLocation = (
  url: string,
  location: BrowserLocation = window.location,
): void => {
  location.assign(url);
};
