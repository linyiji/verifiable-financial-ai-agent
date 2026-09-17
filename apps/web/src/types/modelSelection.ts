import type {Phase4JsonObject} from "../data/FrontendDataSource";
export interface ModelSelectionOption {
  readonly route_id: string;
  readonly label: string;
}

export function modelSelectionPreferences(routeId: string): Phase4JsonObject {
  return routeId === "" ? {} : { model_selection: { route_id: routeId } };
}

export function decodeModelSelectionOptions(value: unknown): readonly ModelSelectionOption[] {
  if (!Array.isArray(value)) throw new TypeError("Invalid model options");
  const ids = new Set<string>();
  return value.map(item => {
    if (!item || typeof item.route_id !== "string" || !item.route_id.trim() ||
        typeof item.label !== "string" || !item.label.trim() || ids.has(item.route_id)) {
      throw new TypeError("Invalid model option");
    }
    ids.add(item.route_id);
    return Object.freeze({route_id: item.route_id, label: item.label});
  });
}
