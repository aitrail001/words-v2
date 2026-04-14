export const locationAssignCalls: string[] = [];
export const locationReplaceCalls: string[] = [];

export const recordLocationAssign = (url: string): void => {
  locationAssignCalls.push(url);
};

export const recordLocationReplace = (url: string): void => {
  locationReplaceCalls.push(url);
};

export const resetLocationSpies = (): void => {
  locationAssignCalls.length = 0;
  locationReplaceCalls.length = 0;
};
