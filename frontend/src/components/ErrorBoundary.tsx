import { Component, type ReactNode } from 'react'
import { StateView } from './StateView'

/** Keeps one failing widget (e.g. a map without WebGL) from blanking the whole dashboard. */
export class ErrorBoundary extends Component<{ what: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (this.state.failed)
      return (
        <StateView kind="unavailable" title={`${this.props.what} could not be drawn`}>
          This browser could not start the component (for example WebGL is disabled). The data is still available in the tables and details.
        </StateView>
      )
    return this.props.children
  }
}
