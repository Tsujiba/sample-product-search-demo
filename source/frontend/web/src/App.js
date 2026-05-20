import React, { Component, createRef } from "react";
import { withAuthenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import { Icon, Link } from "@cloudscape-design/components";
import AgentMain from "./components/agent/agentMain";
import NovaMmeVideoMain from "./components/novaMme/videoMain";
import ProductSearchMain from "./components/productSearch/ProductSearchMain";
import "./App.css";
import About from "./about"
import { FetchPost } from "./resources/data-provider";

const ITEMS = [
  { type: "link", icon: "search", text: "Search", id: "novamme", href: "#/novamme" },
  { type: "link", icon: "shopping-bag", text: "Products", id: "products", href: "#/products" },
  { type: "link", icon: "gen-ai", text: "Chat", id: "chat", href: "#/chat" },
  { type: "split" },
  { type: "link", icon: "support", text: "About", id: "about", href: "#/about" },
];

class App extends Component {
  constructor(props) {
    super(props);

    this.state = {
      currentPage: "chat",
      navigationOpen: true,
      activeNavHref: "#/chat",
      displayTopMenu: window.self === window.top,
      cleanSelectionSignal: null,
      smUrl: null,
      displayLeftMenu: true,
    };

    this.appLayout = createRef();
    this.getReadOnlyUsers = this.getReadOnlyUsers.bind(this);
    this.handleMenuClick = this.handleMenuClick.bind(this);

    const envMenus = process.env.REACT_APP_READONLY_DISPLAY_MENUS
      ? process.env.REACT_APP_READONLY_DISPLAY_MENUS.split(",")
      : [];
    this.displayMenus = envMenus;
  }

  getReadOnlyUsers() {
    if (process.env.REACT_APP_READONLY_USERS)
      return process.env.REACT_APP_READONLY_USERS.toString().split(",");
    else return [];
  }

  handleMenuClick(id) {
    this.setState({
      currentPage: id,
      cleanSelectionSignal: Math.random(),
    });
  }

  render() {
    const { signOut, user } = this.props;
    const { currentPage, displayTopMenu, smUrl, cleanSelectionSignal } = this.state;

    return (
      <div className="app">
        {displayTopMenu && (
          <div className="topmenu">
            <div className="title">Amazon Nova Multi-Modal Embedding Demo</div>
            <div className="user" title={user.email}>
              <Icon name="user-profile-active"></Icon>&nbsp;&nbsp;
              {user.username}
            </div>
          </div>
        )}

        {this.state.displayLeftMenu?<div className="sidemenu">
          <div className="action" onClick={()=>this.setState({displayLeftMenu: false})}>
            <Icon name="angle-left" size="medium"></Icon>
          </div>
          {ITEMS.map((item, index) => {
              if(item.type == "split")
                return <hr className="line"/>
              else if(this.displayMenus.length === 0 || this.displayMenus.includes(item.id)) 
                return <div
                  key={`menu_${index}`}
                  className={item.id === currentPage ? "itemselected" : "item"}
                  onClick={() => this.handleMenuClick(item.id)}
                >
                  {item.icon && <Icon name={item.icon}></Icon>}
                  &nbsp;{item.text}
                </div>
              else 
                return <div key={`empty_${index}`} />
            }
          )}
          <div className="bottom">
            <div className="item" onClick={() => signOut()}>
              Logout
            </div>
          </div>
        </div>:
        <div className="sidemenucollapsed" onClick={()=>this.setState({displayLeftMenu: true})}>
          <div className="icon">
          <Icon name="menu" size="medium" variant="inverted"></Icon>
          </div>
        </div>}

        <div className="content">
          {currentPage === "chat" ? (
            <AgentMain
              cleanSelectionSignal={cleanSelectionSignal}
              readOnlyUsers={this.getReadOnlyUsers()}
            />
          ) : currentPage === "novamme" ? (
            <NovaMmeVideoMain
              cleanSelectionSignal={cleanSelectionSignal}
              readOnlyUsers={this.getReadOnlyUsers()}
            />
          ) : currentPage === "products" ? (
            <ProductSearchMain />
          ) : currentPage === "about" ? <About/>: <div/>

        }
        </div>

      </div>
    );
  }
}

export default withAuthenticator(App);
