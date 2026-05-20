import React, { Component } from 'react';
import { Tabs } from '@cloudscape-design/components';
import ProductSearchPanel from './ProductSearchPanel';
import ProductRegister from './ProductRegister';
import './productSearch.css';

class ProductSearchMain extends Component {
  constructor(props) {
    super(props);
    this.state = { activeTab: "search" };
  }

  render() {
    return (
      <div className="product-search-main">
        <Tabs
          activeTabId={this.state.activeTab}
          onChange={({ detail }) => this.setState({ activeTab: detail.activeTabId })}
          tabs={[
            { id: "search", label: "商品検索", content: <ProductSearchPanel /> },
            { id: "register", label: "商品登録", content: <ProductRegister /> },
          ]}
        />
      </div>
    );
  }
}

export default ProductSearchMain;
