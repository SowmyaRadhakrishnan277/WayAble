import type {Route} from '../api/types';
import DublinMap from './DublinMap';
export default function MapView({route}:{route:Route}){return <details className="map-panel" onToggle={()=>window.dispatchEvent(new Event('resize'))}><summary><MapPinIcon/> Open route map <span>Map is optional; use the step list above.</span></summary><DublinMap route={route} showControls/><div className="map-controls-caption">© OpenStreetMap contributors</div></details>}
function MapPinIcon(){return <span aria-hidden="true" className="map-pin">⌖</span>}
